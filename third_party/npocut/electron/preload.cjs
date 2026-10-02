const { contextBridge, ipcRenderer, webUtils } = require('electron');
contextBridge.exposeInMainWorld('npocut', {
  registerFile: (file) => ipcRenderer.invoke('register-file', webUtils.getPathForFile(file)),
  getConfig: () => ipcRenderer.invoke('desktop-config'),
  openOutput: () => ipcRenderer.invoke('open-output'),
  cancel: () => ipcRenderer.invoke('cancel-job'),
  onLog: (callback) => ipcRenderer.on('job-log', (_event, text) => callback(text)),
  onDone: (callback) => ipcRenderer.on('job-done', (_event, code) => callback(code)),
});
