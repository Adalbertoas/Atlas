import { contextBridge, ipcRenderer } from "electron";
// Eventos que el proceso principal empuja a la ventana; solo los de esta lista.
const EVENTS = new Set(["atlas:chat-event"]);
contextBridge.exposeInMainWorld("atlas", {
  invoke: (channel: string, input?: unknown) => ipcRenderer.invoke("atlas:invoke", channel, input),
  on: (channel: string, listener: (payload: unknown) => void) => {
    if (!EVENTS.has(channel)) throw new Error("Evento no permitido.");
    const handler = (_event: unknown, payload: unknown) => listener(payload);
    ipcRenderer.on(channel, handler);
    return () => { ipcRenderer.removeListener(channel, handler); };
  },
});
export {};