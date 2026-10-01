const { app, BrowserWindow, Menu, Tray, nativeImage, dialog, shell } = require('electron');
const { spawn } = require('node:child_process');
const fs = require('node:fs');
const path = require('node:path');
const http = require('node:http');
let config = {};
const origin = 'http://127.0.0.1:8765';
let win, tray, backend, quitting = false, log;
const loginOptions = { path: process.execPath, args: ['--background'] };
const hasLock = app.requestSingleInstanceLock();
if (!hasLock) app.quit();
async function loadConfiguration() {
  const saved = path.join(app.getPath('userData'), 'runtime.json');
  const bundled = path.join(__dirname, 'runtime.json');
  for (const file of [saved, bundled]) {
    if (fs.existsSync(file)) {
      try { config = JSON.parse(fs.readFileSync(file, 'utf8').replace(/^\uFEFF/, '')); } catch { continue; }
      if (!config || typeof config !== 'object') { config = {}; continue; }
      if (fs.existsSync(path.join(config.projectRoot || '', 'src', 'ontokb', 'cli.py')) && fs.existsSync(config.python || '')) return;
    }
  }
  const project = await dialog.showOpenDialog({ title: '选择 OntoKB 项目目录（需先安装 Python 依赖）', properties: ['openDirectory'] });
  if (project.canceled) throw new Error('尚未配置 OntoKB 项目目录。');
  const projectRoot = project.filePaths[0];
  if (!fs.existsSync(path.join(projectRoot, 'src', 'ontokb', 'cli.py'))) throw new Error('所选目录不是 OntoKB 项目根目录。');
  const python = await dialog.showOpenDialog({ title: '选择已安装 OntoKB 依赖的 python.exe', properties: ['openFile'], filters: [{ name: 'Python', extensions: ['exe'] }] });
  if (python.canceled) throw new Error('尚未配置 Python。');
  config = { projectRoot, python: python.filePaths[0] };
  fs.writeFileSync(saved, JSON.stringify(config, null, 2));
}
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
  const record = message => fs.appendFileSync(path.join(app.getPath('userData'), 'backend.log'), `[${new Date().toISOString()}] ${message}\n`);
  record(`Starting backend: ${config.python}; project: ${config.projectRoot}`);
  backend = spawn(config.python, ['-m', 'ontokb.cli', 'api', '--host', '127.0.0.1', '--port', '8765'], {
    cwd: config.projectRoot, windowsHide: true,
    env: { ...process.env, PYTHONUTF8: '1', PYTHONPATH: path.join(config.projectRoot, 'src'), ONTOKB_LLM_PROVIDER: 'codex' },
    stdio: ['ignore', 'pipe', 'pipe']
  });
  let failure;
  backend.on('error', err => { failure = err; record(`Backend spawn error: ${err.stack || err.message}`); });
  backend.stdout.pipe(log, { end: false }); backend.stderr.pipe(log, { end: false });
  backend.on('close', () => log.end());
  backend.on('exit', (code, signal) => {
    record(`Backend exited: code=${code}, signal=${signal}, quitting=${quitting}`);
    if (win && !quitting) dialog.showErrorBox('OntoKB 后端已停止', `退出码：${code}。请退出后重新打开程序。日志：${app.getPath('userData')}\\backend.log`);
  });
  for (let i = 0; i < 60; i++) {
    if (failure) throw failure;
    if (backend.exitCode !== null || backend.signalCode !== null) throw new Error(`后端启动失败（退出码：${backend.exitCode}，信号：${backend.signalCode || '无'}），请检查 backend.log`);
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
      { label: '探索图谱', click: () => { show(); win?.webContents.executeJavaScript("document.getElementById('explore-nav')?.click()"); } },
      { label: '整理知识', accelerator: 'CmdOrCtrl+Shift+E', click: () => { show(); win?.webContents.executeJavaScript("window.KnowledgeEditor?.open()"); } }
    ] },
    { label: '编辑', submenu: [{ role: 'undo' }, { role: 'redo' }, { type: 'separator' }, { role: 'cut' }, { role: 'copy' }, { role: 'paste' }, { role: 'selectAll' }] },
    { label: '视图', submenu: [{ role: 'reload' }, { label: '强制加载最新界面', accelerator: 'CmdOrCtrl+Shift+R', click: async () => {
      if (!win) return;
      const answer = await dialog.showMessageBox(win, { type: 'question', message: '重新加载最新界面？', detail: '未保存的正文或聊天草稿会丢失，请先保存。', buttons: ['取消', '重新加载'], defaultId: 0, cancelId: 0 });
      if (answer.response === 1) win.webContents.reloadIgnoringCache();
    } }, { role: 'resetZoom' }, { role: 'zoomIn' }, { role: 'zoomOut' }, { role: 'togglefullscreen' }] }]));
}
app.on('second-instance', show);
app.on('before-quit', () => { quitting = true; if (backend && backend.exitCode === null) backend.kill(); });
app.on('window-all-closed', () => {});
if (hasLock) app.whenReady().then(async () => {
  app.setAppUserModelId('OntoKB.Desktop');
  await loadConfiguration();
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
