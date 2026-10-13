import { contextBridge, ipcRenderer } from "electron";
contextBridge.exposeInMainWorld("atlas", { invoke: (channel: string, input?: unknown) => ipcRenderer.invoke("atlas:invoke", channel, input) });
export {};