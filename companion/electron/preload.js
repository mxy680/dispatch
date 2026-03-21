import { contextBridge, ipcRenderer } from "electron";

contextBridge.exposeInMainWorld("dispatchCompanion", {
  getConfig: () => ipcRenderer.invoke("dispatch.get-config"),
  pairDevice: (args) => ipcRenderer.invoke("dispatch.pair-device", args),
  selectProjectDirectory: () => ipcRenderer.invoke("dispatch.select-project-directory"),
  linkProject: (args) => ipcRenderer.invoke("dispatch.link-project", args),
  getLinkedProjects: () => ipcRenderer.invoke("dispatch.get-linked-projects"),
  openCursor: (args) => ipcRenderer.invoke("dispatch.open-cursor", args),
});

