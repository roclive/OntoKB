const { app, BrowserWindow, Menu, Tray, nativeImage, dialog, shell } = require('electron');
const { spawn } = require('node:child_process');
const fs = require('node:fs');
const path = require('node:path');
const http = require('node:http');
const config = JSON.parse(fs.readFileSync(path.join(__dirname, 'runtime.json'), 'utf8'));
const origin = 'http://127.0.0.1:8765';
let win, tray, backend, quitting = false, log;
const loginOptions = { path: process.execPath, args: ['--background'] };
const hasLock = app.requestSingleInstanceLock();
if (!hasLock) app.quit();
function health() {
  return new Promise(resolve => {
    const req = http.get(`${origin}/health`, res => {
      let body = ''; res.on('data', chunk => body += chunk);
      res.on('end', () => { try { const data = JSON.parse(body); resolve(res.statusCode === 200 && data.ok === true && data.chat === true ? data : null); } catch { resolve(null); } });
    });
    req.setTimeout(1500, () => req.destroy());
    req.on('error', () => resolve(false));
  });
}
async function ensureBackend() {
  const existing = await health();
  if (existing) {
    if (existing.app_id !== 'ontokb' || !existing.features?.summary_walk || !existing.features?.article_summary)
      throw new Error('8765 端口上的后端版本较旧。请停止旧的 ontokb api 后重新打开桌面程序，以启用文章摘要与图谱漫游。');
    return;
  }
  log = fs.createWriteStream(path.join(app.getPath('userData'), 'backend.log'), { flags: 'a' });
  backend = spawn(config.python, ['-m', 'ontokb.cli', 'api', '--host', '127.0.0.1', '--port', '8765'], {
    cwd: config.projectRoot, windowsHide: true,
    env: { ...process.env, PYTHONUTF8: '1', PYTHONPATH: path.join(config.projectRoot, 'src'), ONTOKB_LLM_PROVIDER: 'codex' },
    stdio: ['ignore', 'pipe', 'pipe']
  });
  let failure;
  backend.on('error', err => failure = err);
  backend.stdout.pipe(log); backend.stderr.pipe(log);
  backend.on('exit', code => {
    if (win && !quitting) dialog.showErrorBox('OntoKB 后端已停止', `退出码：${code}。请退出后重新打开程序。日志：${app.getPath('userData')}\\backend.log`);
  });
  for (let i = 0; i < 60; i++) {
    if (failure) throw failure;
    if (backend.exitCode !== null) throw new Error('后端启动失败，请检查 backend.log');
    if (await health()) return;
    await new Promise(resolve => setTimeout(resolve, 500));
  }
  throw new Error('等待后端启动超时，请检查 backend.log');
}
function show() { if (win) { win.show(); if (win.isMinimized()) win.restore(); win.focus(); } }
function menus() {
  const items = [
    { label: '打开 OntoKB', click: show },
    { label: '开机自动启动', type: 'checkbox', checked: app.getLoginItemSettings(loginOptions).openAtLogin,
      click: item => { app.setLoginItemSettings({ ...loginOptions, openAtLogin: item.checked }); menus(); } },
    { label: '打开项目目录', click: () => shell.openPath(config.projectRoot) },
    { label: '打开日志目录', click: () => shell.openPath(app.getPath('userData')) },
    { type: 'separator' }, { label: '退出', click: () => app.quit() }
  ];
  tray.setContextMenu(Menu.buildFromTemplate(items));
  Menu.setApplicationMenu(Menu.buildFromTemplate([{ label: 'OntoKB', submenu: items },
    { label: '阅读', submenu: [
      { label: '新建文章摘要', accelerator: 'CmdOrCtrl+N', click: () => { show(); win?.webContents.executeJavaScript("document.getElementById('article-open')?.click()"); } },
      { label: '阅读工作台', click: () => { show(); win?.webContents.executeJavaScript("document.getElementById('reading-nav')?.click()"); } },
      { label: '探索图谱', click: () => { show(); win?.webContents.executeJavaScript("document.getElementById('explore-nav')?.click()"); } }
    ] },
    { label: '编辑', submenu: [{ role: 'undo' }, { role: 'redo' }, { type: 'separator' }, { role: 'cut' }, { role: 'copy' }, { role: 'paste' }, { role: 'selectAll' }] },
    { label: '视图', submenu: [{ role: 'reload' }, { role: 'resetZoom' }, { role: 'zoomIn' }, { role: 'zoomOut' }, { role: 'togglefullscreen' }] }]));
}
app.on('second-instance', show);
app.on('before-quit', () => { quitting = true; if (backend && backend.exitCode === null) backend.kill(); });
app.on('window-all-closed', () => {});
if (hasLock) app.whenReady().then(async () => {
  app.setAppUserModelId('OntoKB.Desktop');
  const pixels = Buffer.alloc(32 * 32 * 4);
  for (let i = 0; i < pixels.length; i += 4) { pixels[i] = 190; pixels[i+1] = 120; pixels[i+2] = 45; pixels[i+3] = 255; }
  tray = new Tray(nativeImage.createFromBitmap(pixels, { width: 32, height: 32 }));
  tray.setToolTip('OntoKB — 知识库后台运行中'); tray.on('double-click', show);
  const initialized = path.join(app.getPath('userData'), 'desktop-initialized');
  if (app.isPackaged && !fs.existsSync(initialized)) {
    app.setLoginItemSettings({ ...loginOptions, openAtLogin: true });
    fs.writeFileSync(initialized, '1');
  }
  menus();
  await ensureBackend();
  win = new BrowserWindow({ width: 1440, height: 940, minWidth: 900, minHeight: 600, title: 'OntoKB · 知识漫游', backgroundColor: '#f5f4ef',
    show: false, webPreferences: { nodeIntegration: false, contextIsolation: true, sandbox: true } });
  win.on('close', event => { if (!quitting) { event.preventDefault(); win.hide(); } });
  const external = url => { if (/^https?:\/\//i.test(url)) shell.openExternal(url); };
  win.webContents.setWindowOpenHandler(({ url }) => { external(url); return { action: 'deny' }; });
  win.webContents.on('will-navigate', (event, url) => { if (new URL(url).origin !== origin) { event.preventDefault(); external(url); } });
  await win.loadURL(origin);
  if (!process.argv.includes('--background')) show();
}).catch(err => { dialog.showErrorBox('OntoKB 启动失败', `${err.message}\n项目：${config.projectRoot}\n日志：${app.getPath('userData')}\\backend.log`); app.quit(); });
