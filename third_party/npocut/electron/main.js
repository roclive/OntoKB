import { app, BrowserWindow, ipcMain, dialog, shell, Menu } from 'electron';
import { mkdir, stat } from 'node:fs/promises';
import { basename, dirname, extname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { randomBytes } from 'node:crypto';
import { spawn } from 'node:child_process';
import { createAppServer } from '../server.js';
import { parseCommand } from './commands.js';

const here = dirname(fileURLToPath(import.meta.url));
const resources = app.isPackaged ? process.resourcesPath : join(here, '..');
const runtime = join(resources, 'runtime');
const scriptsDir = join(runtime, 'scripts');
const media = new Map();
const token = randomBytes(32).toString('hex');
let window, server, job, workspace, origin;

function send(channel, value) {
  if (window && !window.isDestroyed()) window.webContents.send(channel, value);
}
function cancelJob() {
  if (!job) return;
  if (process.platform === 'win32') spawn('taskkill', ['/pid', String(job.pid), '/T', '/F'], { windowsHide: true });
  else job.kill();
}
function runCommand(command) {
  if (job) throw new Error('A task is already running. Wait or cancel it first.');
  const args = parseCommand(command, scriptsDir, media, workspace);
  const python = join(runtime, 'python', 'python.exe');
  const env = { ...process.env, PYTHONIOENCODING: 'utf-8', PYTHONUNBUFFERED: '1',
    NPOCUT_FFMPEG: join(runtime, 'ffmpeg.exe'), NPOCUT_FFPROBE: join(runtime, 'ffprobe.exe'),
    PATH: `${runtime};${process.env.PATH}`, HF_HOME: join(app.getPath('userData'), 'models') };
  return new Promise((resolve, reject) => {
    const child = spawn(python, ['-s', '-u', ...args], { cwd: workspace, env, windowsHide: true, shell: false });
    job = child;
    child.once('spawn', resolve);
    child.stdout.on('data', data => send('job-log', data.toString()));
    child.stderr.on('data', data => send('job-log', data.toString()));
    child.once('error', error => { send('job-log', error.message); reject(error); });
    child.once('close', code => { if (job === child) job = null; send('job-done', code); });
  });
}
function trusted(handler) {
  return (event, ...args) => {
    if (event.sender !== window?.webContents || event.senderFrame.url !== `${origin}/`) throw new Error('Untrusted sender');
    return handler(...args);
  };
}
if (!app.requestSingleInstanceLock()) app.quit();
else {
  app.on('second-instance', () => { if (window) { if (window.isMinimized()) window.restore(); window.focus(); } });
  app.whenReady().then(async () => {
    workspace = process.env.NPOCUT_WORKSPACE ? resolve(process.env.NPOCUT_WORKSPACE) : join(app.getPath('documents'), 'npocut');
    await mkdir(workspace, { recursive: true });
    server = createAppServer({ workspace, runCommand, token, onSave: (name, path) => media.set(name, path) });
    await new Promise((resolve, reject) => { server.once('error', reject); server.listen(0, '127.0.0.1', resolve); });
    origin = `http://127.0.0.1:${server.address().port}`;
    window = new BrowserWindow({ width: 1440, height: 960, minWidth: 960, minHeight: 640,
      title: 'npocut', webPreferences: { preload: join(here, 'preload.cjs'),
        contextIsolation: true, nodeIntegration: false, sandbox: true } });
    Menu.setApplicationMenu(null);
    window.webContents.setWindowOpenHandler(() => ({ action: 'deny' }));
    window.webContents.on('will-navigate', (event, url) => { if (url !== `${origin}/`) event.preventDefault(); });
    window.webContents.session.setPermissionRequestHandler((_wc, _permission, callback) => callback(false));
    ipcMain.handle('desktop-config', trusted(() => ({ token, workspace })));
    ipcMain.handle('register-file', trusted(async path => {
      if (!path || !['.mp4', '.mov', '.mkv', '.webm', '.avi', '.m4v', '.srt'].includes(extname(path).toLowerCase()) || !(await stat(path)).isFile()) throw new Error('Unsupported media file');
      media.set(basename(path), path);
      return basename(path);
    }));
    ipcMain.handle('open-output', trusted(() => shell.openPath(workspace)));
    ipcMain.handle('cancel-job', trusted(cancelJob));
    window.on('close', event => {
      if (job && dialog.showMessageBoxSync(window, { type: 'question', buttons: ['Continue working', 'Cancel task and exit'], defaultId: 0, cancelId: 0, message: 'A video task is running. Cancel it and exit?' }) === 0) event.preventDefault();
    });
    await window.loadURL(`${origin}/`);
  }).catch(error => { dialog.showErrorBox('npocut startup failed', error.stack || error.message); app.quit(); });
  app.on('before-quit', () => { cancelJob(); server?.close(); });
  app.on('window-all-closed', () => app.quit());
}
