import { app, BrowserWindow, dialog, ipcMain, session } from "electron";
import path from "node:path";
import { fileURLToPath } from "node:url";
const __dirname = path.dirname(fileURLToPath(import.meta.url));
import os from "node:os";
import { execFile } from "node:child_process";
import { promisify } from "node:util";
const exec = promisify(execFile);
let window: BrowserWindow | null = null;
const allow = new Set(["system:status", "system:processes", "files:pick", "atlas:chat", "atlas:service-status", "atlas:transcribe", "atlas:speak", "layout:load", "layout:save"]);
const MAX_AUDIO_BYTES = 25 * 1024 * 1024;
const layoutPath = () => path.join(app.getPath("userData"), "atlas-layout.json");
const atlasApiUrl = (process.env.ATLAS_API_URL ?? "http://127.0.0.1:8000").replace(/\/$/, "");
let atlasToken: string | null = null;
async function powershell(script: string) { const { stdout } = await exec("powershell.exe", ["-NoProfile", "-NonInteractive", "-Command", script], { windowsHide: true, timeout: 5000 }); return stdout.trim(); }
async function systemStatus() {
  const cpus = os.cpus(); const memory = { used: os.totalmem() - os.freemem(), total: os.totalmem() };
  let cpuUsage = 0; try { cpuUsage = Number(await powershell("(Get-Counter '\\Processor(_Total)\\% Processor Time').CounterSamples[0].CookedValue")); } catch {}
  let disks: unknown = null; let gpu: unknown = null;
  try { disks = JSON.parse(await powershell("Get-CimInstance Win32_LogicalDisk -Filter 'DriveType=3' | Select-Object DeviceID,Size,FreeSpace | ConvertTo-Json -Compress")); } catch {}
  try { gpu = JSON.parse(await powershell("Get-CimInstance Win32_VideoController | Select-Object Name,AdapterRAM | ConvertTo-Json -Compress")); } catch {}
  return { cpu: { cores: cpus.length, model: cpus[0]?.model ?? "No disponible", load: cpuUsage / 100 }, memory, disks, gpu, uptime: os.uptime() };
}
async function serviceStatus() {
  const endpoint = `${atlasApiUrl}/api/v1/system/health`;
  try {
    const response = await fetch(endpoint, { signal: AbortSignal.timeout(1500) });
    if (!response.ok) return { available: false };
    const body = await response.json() as { ai_provider?: string };
    return { available: true, provider: body.ai_provider ?? null };
  } catch { return { available: false }; }
}
async function atlasLogin() {
  if (atlasToken) return atlasToken;
  const response = await fetch(`${atlasApiUrl}/api/v1/auth/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ password: process.env.ATLAS_PASSWORD ?? "" }),
    signal: AbortSignal.timeout(5000),
  });
  if (!response.ok) {
    throw new Error(response.status === 401
      ? "El backend requiere ATLAS_PASSWORD. Configurala como variable de entorno antes de iniciar Electron."
      : `No se pudo iniciar sesion con el backend (HTTP ${response.status}).`);
  }
  const body = await response.json() as { access_token?: string };
  if (!body.access_token) throw new Error("El backend no devolvio un token de sesion valido.");
  atlasToken = body.access_token;
  return atlasToken;
}
async function atlasChat(input: unknown) {
  const message = typeof (input as { message?: unknown })?.message === "string" ? (input as { message: string }).message.trim() : "";
  if (!message) throw new Error("El mensaje no puede estar vacio.");
  const token = await atlasLogin();
  const response = await fetch(`${atlasApiUrl}/api/v1/chat`, {
    method: "POST",
    headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
    body: JSON.stringify({ message }),
    signal: AbortSignal.timeout(65000),
  });
  if (response.status === 401) { atlasToken = null; throw new Error("La sesion con ATLAS expiro. Intenta de nuevo."); }
  if (!response.ok) throw new Error(`El backend no pudo completar la consulta (HTTP ${response.status}).`);
  const body = await response.json() as { reply?: string; requires_confirmation?: boolean; confirmation_description?: string };
  const confirmation = body.requires_confirmation ? `\n\nConfirmacion requerida: ${body.confirmation_description ?? "Revisa la accion en el cliente de escritorio."}` : "";
  return { configured: true, text: `${body.reply ?? "Sin respuesta."}${confirmation}`, requiresConfirmation: Boolean(body.requires_confirmation) };
}
// Voz: el renderer graba y reproduce; aqui solo se reenvia a los endpoints de voz
// que ya expone el backend, con la misma sesion que el chat. El audio no se guarda.
async function atlasVoiceRequest(path: string, init: RequestInit, timeoutMs: number) {
  const token = await atlasLogin();
  const response = await fetch(`${atlasApiUrl}/api/v1/voice/${path}`, { ...init, headers: { ...init.headers, Authorization: `Bearer ${token}` }, signal: AbortSignal.timeout(timeoutMs) });
  if (response.status === 401) { atlasToken = null; throw new Error("La sesion con ATLAS expiro. Intenta de nuevo."); }
  if (!response.ok) throw new Error(`El servicio de voz no pudo completar la operacion (HTTP ${response.status}).`);
  return response;
}
async function atlasTranscribe(input: unknown) {
  const { audio, mimeType } = (input ?? {}) as { audio?: unknown; mimeType?: unknown };
  if (!(audio instanceof Uint8Array) || !audio.byteLength) throw new Error("No hay audio para transcribir.");
  if (audio.byteLength > MAX_AUDIO_BYTES) throw new Error("La grabacion es demasiado larga.");
  const type = typeof mimeType === "string" && /^audio\/[\w.+-]+(;.*)?$/.test(mimeType) ? mimeType : "audio/webm";
  const form = new FormData();
  form.append("audio", new Blob([new Uint8Array(audio)], { type }), "audio.webm");
  const response = await atlasVoiceRequest("transcribe", { method: "POST", body: form }, 60000);
  const body = await response.json() as { text?: string };
  return { text: body.text ?? "" };
}
async function atlasSpeak(input: unknown) {
  const text = typeof (input as { text?: unknown })?.text === "string" ? (input as { text: string }).text.trim() : "";
  if (!text) throw new Error("No hay texto para sintetizar.");
  const response = await atlasVoiceRequest("speak", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ text }) }, 90000);
  return new Uint8Array(await response.arrayBuffer());
}
// Electron concede por defecto cualquier permiso que pida la pagina. Se limita a
// camara y microfono, y solo para la ventana de ATLAS; el consentimiento del
// usuario se pide en la interfaz antes de llegar aqui.
function restrictPermissions() {
  session.defaultSession.setPermissionRequestHandler((webContents, permission, callback) => {
    callback(permission === "media" && webContents === window?.webContents);
  });
}
function createWindow() { window = new BrowserWindow({ width: 1536, height: 960, minWidth: 1080, minHeight: 700, backgroundColor: "#030a12", title: "ATLAS", webPreferences: { preload: path.join(__dirname, "preload.cjs"), contextIsolation: true, nodeIntegration: false, sandbox: true } }); const url = process.env.VITE_DEV_SERVER_URL; if (url) window.loadURL(url); else window.loadFile(path.join(__dirname, "../dist/index.html")); }
app.whenReady().then(() => { ipcMain.handle("atlas:invoke", async (_event, channel: string, input?: unknown) => { if (!allow.has(channel)) throw new Error("Operación no permitida."); if (channel === "system:status") return systemStatus(); if (channel === "system:processes") { try { return JSON.parse(await powershell("Get-Process | Sort-Object CPU -Descending | Select-Object -First 30 ProcessName,Id,CPU,WorkingSet64 | ConvertTo-Json -Compress")); } catch { return []; } } if (channel === "files:pick") { const picked = await dialog.showOpenDialog({ properties: ["openFile", "multiSelections"] }); return picked.canceled ? [] : picked.filePaths.map((filePath) => path.basename(filePath)); } if (channel === "layout:load") { try { return JSON.parse(await (await import("node:fs/promises")).readFile(layoutPath(), "utf8")); } catch { return null; } } if (channel === "layout:save") { await (await import("node:fs/promises")).writeFile(layoutPath(), JSON.stringify(input)); return true; } if (channel === "atlas:service-status") return serviceStatus(); if (channel === "atlas:chat") return atlasChat(input); if (channel === "atlas:transcribe") return atlasTranscribe(input); if (channel === "atlas:speak") return atlasSpeak(input); return null; }); restrictPermissions(); createWindow(); app.on("activate", () => { if (!BrowserWindow.getAllWindows().length) createWindow(); }); }); app.on("window-all-closed", () => { if (process.platform !== "darwin") app.quit(); });
