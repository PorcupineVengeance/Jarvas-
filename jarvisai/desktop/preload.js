const { contextBridge, ipcRenderer } = require('electron');

contextBridge.exposeInMainWorld('jarvisDesktop', {
  isDesktop: true,
  platform: process.platform,
  getInfo: () => ipcRenderer.invoke('desktop:get-info'),
  pickFolders: () => ipcRenderer.invoke('desktop:pick-folders'),
  revealDataDir: () => ipcRenderer.invoke('desktop:reveal-data-dir'),
  ensureMicrophone: () => ipcRenderer.invoke('desktop:ensure-microphone'),
  openMicrophoneSettings: () => ipcRenderer.invoke('desktop:open-microphone-settings'),
  onAssistantOnline: () => ipcRenderer.invoke('desktop:assistant-online'),
  onAssistantStandby: () => ipcRenderer.invoke('desktop:assistant-standby'),
});
