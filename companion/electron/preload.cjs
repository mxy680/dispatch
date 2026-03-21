const { contextBridge, ipcRenderer } = require("electron");

contextBridge.exposeInMainWorld("dispatchCompanion", {
  getAppInfo: () => ipcRenderer.invoke("dispatch.get-app-info"),
  getConfig: () => ipcRenderer.invoke("dispatch.get-config"),
  pairDevice: (args) => ipcRenderer.invoke("dispatch.pair-device", args),
  selectProjectDirectory: () => ipcRenderer.invoke("dispatch.select-project-directory"),
  linkProject: (args) => ipcRenderer.invoke("dispatch.link-project", args),
  getLinkedProjects: () => ipcRenderer.invoke("dispatch.get-linked-projects"),
  getProjectBasePath: () => ipcRenderer.invoke("dispatch.get-project-base-path"),
  setProjectBasePath: (args) => ipcRenderer.invoke("dispatch.set-project-base-path", args),
  openCursor: (args) => ipcRenderer.invoke("dispatch.open-cursor", args),
  resetConnection: () => ipcRenderer.invoke("dispatch.reset-connection"),
});

