import { app, BrowserWindow, dialog, ipcMain, net, session, shell } from "electron";
import { readFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
const __dirname = path.dirname(fileURLToPath(import.meta.url));
import os from "node:os";
import { execFile, spawn, type ChildProcess } from "node:child_process";
import { createWriteStream, existsSync, mkdirSync } from "node:fs";
import { promisify } from "node:util";
const exec = promisify(execFile);
// App instalada: el backend viaja dentro del instalador (resources/backend, con
// un Python portable en resources/python y los modelos en resources/models) y
// se arranca aqui, en http local. Los datos que cambian (base de datos, huella
// de voz, log) van a la carpeta de usuario para sobrevivir a reinstalaciones.
const bundled = app.isPackaged && existsSync(path.join(process.resourcesPath, "backend", "app"));
function readDotEnv(file: string) {
  const values: Record<string, string> = {};
  try {
    for (const line of readFileSync(file, "utf8").split(/\r?\n/)) {
      const match = /^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*?)\s*$/.exec(line);
      if (match) values[match[1]] = match[2].replace(/^(["'])(.*)\1$/, "$2");
    }
  } catch {}
  return values;
}
const bundledEnv = bundled ? readDotEnv(path.join(process.resourcesPath, "backend", ".env")) : {};
if (bundled) {
  // Carpeta propia: sin esto comparte perfil con `npm run dev` (mismo nombre de paquete).
  app.setPath("userData", path.join(app.getPath("appData"), "ATLAS"));
  process.env.ATLAS_API_URL ??= "http://127.0.0.1:8000";
  process.env.ATLAS_CERT_PATH ??= path.join(process.resourcesPath, "no-cert.pem");
  if (bundledEnv.ATLAS_PASSWORD) process.env.ATLAS_PASSWORD ??= bundledEnv.ATLAS_PASSWORD;
}
let backendProcess: ChildProcess | null = null;
function startBundledBackend() {
  const resources = process.resourcesPath;
  const dataDir = app.getPath("userData");
  mkdirSync(dataDir, { recursive: true });
  const log = createWriteStream(path.join(dataDir, "backend.log"), { flags: "a" });
  const models = path.join(resources, "models");
  backendProcess = spawn(path.join(resources, "python", "python.exe"), ["-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", new URL(process.env.ATLAS_API_URL ?? "http://127.0.0.1:8000").port || "8000"], {
    cwd: path.join(resources, "backend"),
    windowsHide: true,
    env: {
      ...process.env,
      PYTHONUNBUFFERED: "1",
      PYTHONIOENCODING: "utf-8",
      PYTHONNOUSERSITE: "1",
      HF_HOME: path.join(models, "huggingface"),
      HF_HUB_OFFLINE: "1",
      KOKORO_CACHE_DIR: path.join(models, "huggingface"),
      SPEAKER_MODEL_PATH: path.join(models, "speaker", "voxceleb_resnet34_LM.onnx"),
      SPEAKER_PROFILE_PATH: path.join(dataDir, "speaker_profile.json"),
      DATABASE_URL: `sqlite:///${path.join(dataDir, "atlas.db").replace(/\\/g, "/")}`,
    },
  });
  backendProcess.stdout?.pipe(log);
  backendProcess.stderr?.pipe(log);
  backendProcess.on("exit", (code) => { log.write(`\n[atlas] backend termino (codigo ${code})\n`); backendProcess = null; });
}
function stopBundledBackend() {
  if (!backendProcess?.pid) return;
  try { execFile("taskkill", ["/PID", String(backendProcess.pid), "/T", "/F"], { windowsHide: true }); } catch {}
  backendProcess = null;
}
let window: BrowserWindow | null = null;
const allow = new Set(["system:status", "system:processes", "files:pick", "atlas:chat", "atlas:confirm", "atlas:api","atlas:service-status", "atlas:transcribe", "atlas:speak", "atlas:speaker-status", "atlas:speaker-enroll", "atlas:speaker-delete", "layout:load", "layout:save", "creative:open-folder"]);
const MAX_AUDIO_BYTES = 25 * 1024 * 1024;
const layoutPath = () => path.join(app.getPath("userData"), "atlas-layout.json");
// El backend sirve HTTPS con un certificado autofirmado de desarrollo cuando
// existe certs/dev-cert.pem (backend/run.py). En ese caso se usa https y se
// confía exactamente en ese certificado, igual que el cliente de escritorio en
// Python; si no existe, http como antes. ATLAS_API_URL/ATLAS_CERT_PATH lo fuerzan.
const devCertPath = process.env.ATLAS_CERT_PATH ?? path.resolve(__dirname, "../../../certs/dev-cert.pem");
const devCertificate = (() => { try { return readFileSync(devCertPath, "utf8"); } catch { return null; } })();
const atlasApiUrl = (process.env.ATLAS_API_URL ?? `${devCertificate ? "https" : "http"}://127.0.0.1:8000`).replace(/\/$/, "");
const backendHost = new URL(atlasApiUrl).hostname;
const pemBody = (pem: string) => pem.replace(/-----[^-]+-----/g, "").replace(/\s+/g, "");
// Peticiones al backend por la pila de red de Chromium (net.fetch): así se les
// aplica la verificación de certificado de la sesión, configurada abajo.
// FormData se serializa a mano porque net.fetch no lo codifica.
async function backendFetch(url: string, init: RequestInit = {}) {
  if (init.body instanceof FormData) {
    const encoded = new Response(init.body);
    init = { ...init, body: await encoded.arrayBuffer(), headers: { ...(init.headers as Record<string, string>), "Content-Type": encoded.headers.get("content-type") ?? "multipart/form-data" } };
  }
  return net.fetch(url, init);
}
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
    const response = await backendFetch(endpoint, { signal: AbortSignal.timeout(1500) });
    if (!response.ok) return { available: false };
    const body = await response.json() as { ai_provider?: string };
    return { available: true, provider: body.ai_provider ?? null };
  } catch { return { available: false }; }
}
// El backend empaquetado tarda en arrancar (Python, torch, modelos): las peticiones
// esperan a que responda /health en vez de fallar si el usuario escribe antes.
let backendReady: Promise<void> = Promise.resolve();
async function ensureBundledBackend() {
  if ((await serviceStatus()).available) return;
  startBundledBackend();
  const deadline = Date.now() + 120000;
  while (Date.now() < deadline && backendProcess) {
    if ((await serviceStatus()).available) return;
    await new Promise((resolve) => setTimeout(resolve, 1000));
  }
}
async function atlasLogin() {
  await backendReady;
  if (atlasToken) return atlasToken;
  const response = await backendFetch(`${atlasApiUrl}/api/v1/auth/login`, {
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
type ChatImage = { mime_type: string; data: string };
async function atlasChat(input: unknown) {
  const message = typeof (input as { message?: unknown })?.message === "string" ? (input as { message: string }).message.trim() : "";
  if (!message) throw new Error("El mensaje no puede estar vacio.");
  // La misma conversación entre mensajes: sin esto ATLAS olvidaba lo dicho un mensaje antes.
  const conversationId = typeof (input as { conversationId?: unknown })?.conversationId === "string" ? (input as { conversationId: string }).conversationId : undefined;
  const token = await atlasLogin();
  const response = await backendFetch(`${atlasApiUrl}/api/v1/chat`, {
    method: "POST",
    headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
    body: JSON.stringify({ message, conversation_id: conversationId }),
    signal: AbortSignal.timeout(180000), // con imágenes o dibujos la respuesta puede tardar
  });
  if (response.status === 401) { atlasToken = null; throw new Error("La sesion con ATLAS expiro. Intenta de nuevo."); }
  if (!response.ok) throw new Error(`El backend no pudo completar la consulta (HTTP ${response.status}).`);
  const body = await response.json() as { reply?: string; conversation_id?: string; requires_confirmation?: boolean; confirmation_id?: string; confirmation_description?: string; images?: ChatImage[] };
  return {
    configured: true,
    text: body.reply ?? (body.requires_confirmation ? "" : "Sin respuesta."),
    conversationId: body.conversation_id,
    requiresConfirmation: Boolean(body.requires_confirmation),
    confirmationId: body.confirmation_id,
    confirmationDescription: body.confirmation_description,
    images: body.images ?? [],
  };
}
// Aprobar o rechazar una acción que el backend dejó pendiente de confirmación.
async function atlasConfirm(input: unknown) {
  const { confirmationId, approve } = (input ?? {}) as { confirmationId?: unknown; approve?: unknown };
  if (typeof confirmationId !== "string" || !confirmationId) throw new Error("Falta la confirmacion.");
  const token = await atlasLogin();
  const response = await backendFetch(`${atlasApiUrl}/api/v1/chat/confirm`, {
    method: "POST",
    headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
    body: JSON.stringify({ confirmation_id: confirmationId, approve: approve !== false }),
    signal: AbortSignal.timeout(180000), // con imágenes o dibujos la respuesta puede tardar
  });
  if (response.status === 401) { atlasToken = null; throw new Error("La sesion con ATLAS expiro. Intenta de nuevo."); }
  if (!response.ok) throw new Error(`No se pudo confirmar la accion (HTTP ${response.status}).`);
  const body = await response.json() as { reply?: string; images?: ChatImage[] };
  return { text: body.reply ?? "", images: body.images ?? [] };
}
// Paneles del escritorio (memoria, recordatorios, actividad, personalidad, widgets):
// solo estas rutas y métodos, para que el renderer no pueda usar todo el backend.
const apiRoutes: [string, RegExp][] = [
  ["GET", /^\/settings\/personality$/], ["PUT", /^\/settings\/personality$/],
  ["GET", /^\/settings\/keys$/], ["PUT", /^\/settings\/keys$/],
  ["GET", /^\/memory$/], ["GET", /^\/memory\/search$/], ["POST", /^\/memory$/], ["DELETE", /^\/memory\/\d+$/],
  ["GET", /^\/reminders$/], ["DELETE", /^\/reminders\/\d+$/],
  ["GET", /^\/system\/activity$/], ["GET", /^\/tools$/],
  ["GET", /^\/notifications$/], ["PATCH", /^\/notifications\/\d+\/read$/],
  ["GET", /^\/widgets\/(weather|news)$/],
  ["GET", /^\/creative\/engines$/], ["POST", /^\/creative\/(image|enhance)$/],
  ["GET", /^\/creative\/gallery$/], ["GET", /^\/creative\/gallery\/[0-9a-f]{32}$/], ["DELETE", /^\/creative\/gallery\/[0-9a-f]{32}$/],
];
// Generar una imagen (OpenAI) o un dibujo (Claude) puede tardar más de un minuto.
const slowApiRoutes = /^\/creative\/(image|enhance)$/;
async function atlasApi(input: unknown) {
  const { method = "GET", path: route, query, body } = (input ?? {}) as { method?: string; path?: string; query?: Record<string, string | number>; body?: unknown };
  if (typeof route !== "string" || !apiRoutes.some(([m, pattern]) => m === method && pattern.test(route))) throw new Error("Operación no permitida.");
  const url = new URL(`${atlasApiUrl}/api/v1${route}`);
  for (const [key, value] of Object.entries(query ?? {})) url.searchParams.set(key, String(value));
  const token = await atlasLogin();
  const response = await backendFetch(url.toString(), {
    method,
    headers: { ...(body === undefined ? {} : { "Content-Type": "application/json" }), Authorization: `Bearer ${token}` },
    body: body === undefined ? undefined : JSON.stringify(body),
    signal: AbortSignal.timeout(slowApiRoutes.test(route) ? 180000 : 20000),
  });
  if (response.status === 401) { atlasToken = null; throw new Error("La sesion con ATLAS expiro. Intenta de nuevo."); }
  const text = await response.text();
  let data: unknown = null;
  try { data = text ? JSON.parse(text) : null; } catch { data = text; }
  if (!response.ok) {
    const detail = (data as { detail?: unknown })?.detail;
    throw new Error(typeof detail === "string" ? detail : `El backend respondio HTTP ${response.status}.`);
  }
  return data;
}
// Abre en el Explorador la carpeta de creaciones. La ruta la da el backend, no el
// renderer: así la ventana no puede pedir abrir carpetas arbitrarias.
async function openCreationsFolder() {
  const info = await atlasApi({ method: "GET", path: "/creative/engines" }) as { folder?: string };
  if (!info?.folder) throw new Error("ATLAS no informó la carpeta de creaciones.");
  const error = await shell.openPath(info.folder);
  if (error) throw new Error(error);
  return true;
}
// Voz: el renderer graba y reproduce; aqui solo se reenvia a los endpoints de voz
// que ya expone el backend, con la misma sesion que el chat. El audio no se guarda.
async function atlasVoiceRequest(path: string, init: RequestInit, timeoutMs: number) {
  const token = await atlasLogin();
  const response = await backendFetch(`${atlasApiUrl}/api/v1/voice/${path}`, { ...init, headers: { ...init.headers, Authorization: `Bearer ${token}` }, signal: AbortSignal.timeout(timeoutMs) });
  if (response.status === 401) { atlasToken = null; throw new Error("La sesion con ATLAS expiro. Intenta de nuevo."); }
  if (!response.ok) throw new Error(`El servicio de voz no pudo completar la operacion (HTTP ${response.status}).`);
  return response;
}
async function atlasTranscribe(input: unknown) {
  const { audio, mimeType, fast, prompt, speaker, speakerMin } = (input ?? {}) as { audio?: unknown; mimeType?: unknown; fast?: unknown; prompt?: unknown; speaker?: unknown; speakerMin?: unknown };
  if (!(audio instanceof Uint8Array) || !audio.byteLength) throw new Error("No hay audio para transcribir.");
  if (audio.byteLength > MAX_AUDIO_BYTES) throw new Error("La grabacion es demasiado larga.");
  const type = typeof mimeType === "string" && /^audio\/[\w.+-]+(;.*)?$/.test(mimeType) ? mimeType : "audio/webm";
  const form = new FormData();
  form.append("audio", new Blob([new Uint8Array(audio)], { type }), type.startsWith("audio/wav") ? "audio.wav" : "audio.webm");
  // fast: parcial mientras se habla. prompt: sesga a Whisper hacia "Atlas".
  const query = new URLSearchParams();
  if (fast === true) query.set("fast", "true");
  if (typeof prompt === "string" && prompt.trim()) query.set("prompt", prompt.trim().slice(0, 200));
  // speaker: comparar además con la voz registrada ("solo mi voz").
  if (speaker === true) query.set("speaker", "true");
  // speakerMin: por debajo, el backend ni transcribe (otra voz, la tele…).
  if (speaker === true && typeof speakerMin === "number" && Number.isFinite(speakerMin)) query.set("speaker_min", String(Math.max(-1, Math.min(1, speakerMin))));
  const response = await atlasVoiceRequest(`transcribe${query.size ? `?${query}` : ""}`, { method: "POST", body: form }, 60000);
  const body = await response.json() as { text?: string; speaker_score?: number | null };
  return { text: body.text ?? "", speakerScore: typeof body.speaker_score === "number" ? body.speaker_score : null };
}
// Huella de voz: el backend guarda solo un vector numérico, nunca el audio.
type SpeakerStatus = { available: boolean; enrolled: boolean; samples: number; consistency: number | null };
async function speakerStatus(response: Response): Promise<SpeakerStatus> {
  const body = await response.json() as Partial<SpeakerStatus>;
  return { available: Boolean(body.available), enrolled: Boolean(body.enrolled), samples: body.samples ?? 0, consistency: body.consistency ?? null };
}
async function atlasSpeakerEnroll(input: unknown) {
  const samples = (input as { samples?: unknown })?.samples;
  if (!Array.isArray(samples) || samples.length < 2 || samples.length > 6 || !samples.every((sample) => sample instanceof Uint8Array && sample.byteLength && sample.byteLength <= MAX_AUDIO_BYTES)) throw new Error("Hacen falta entre 2 y 6 frases grabadas.");
  const form = new FormData();
  samples.forEach((sample: Uint8Array, index) => form.append("samples", new Blob([new Uint8Array(sample)], { type: "audio/wav" }), `muestra-${index + 1}.wav`));
  const token = await atlasLogin();
  const response = await backendFetch(`${atlasApiUrl}/api/v1/voice/speaker/enroll`, { method: "POST", body: form, headers: { Authorization: `Bearer ${token}` }, signal: AbortSignal.timeout(60000) });
  if (response.status === 503 || response.status === 422) throw new Error(((await response.json()) as { detail?: string }).detail ?? "No se pudo registrar la voz.");
  if (!response.ok) throw new Error(`No se pudo registrar la voz (HTTP ${response.status}).`);
  return speakerStatus(response);
}
async function atlasSpeakerRequest(method: "GET" | "DELETE") {
  return speakerStatus(await atlasVoiceRequest("speaker", { method }, 10000));
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
function trustDevCertificate() {
  if (!devCertificate) return;
  const expected = pemBody(devCertificate);
  session.defaultSession.setCertificateVerifyProc((request, callback) => {
    // 0 = confiar; -3 = decidir con la verificación normal de Chromium.
    callback(request.hostname === backendHost && pemBody(request.certificate.data) === expected ? 0 : -3);
  });
}
function restrictPermissions() {
  session.defaultSession.setPermissionRequestHandler((webContents, permission, callback) => {
    callback(permission === "media" && webContents === window?.webContents);
  });
}
// `npm run dev` pasa --dev-server=<url>; sin esto Electron cargaba la build vieja de dist/
// en lugar del código en vivo de Vite. VITE_DEV_SERVER_URL (usada por las pruebas E2E) tiene prioridad.
function devServerUrl(): string | undefined {
  if (process.env.VITE_DEV_SERVER_URL) return process.env.VITE_DEV_SERVER_URL;
  if (app.isPackaged) return undefined;
  return process.argv.find(arg => arg.startsWith("--dev-server="))?.slice("--dev-server=".length) || undefined;
}
function createWindow() { window = new BrowserWindow({ width: 1536, height: 960, minWidth: 1080, minHeight: 700, backgroundColor: "#030a12", title: "ATLAS", webPreferences: { preload: path.join(__dirname, "preload.cjs"), contextIsolation: true, nodeIntegration: false, sandbox: true } }); const url = devServerUrl(); if (url) window.loadURL(url); else window.loadFile(path.join(__dirname, "../dist/index.html")); guardNavigation(window); }
// Los enlaces de las respuestas (http/https) se abren en el navegador del sistema;
// la ventana de ATLAS nunca navega fuera de la app ni abre ventanas propias.
function guardNavigation(win: BrowserWindow) {
  const external = (target: string) => { try { const { protocol } = new URL(target); if (protocol === "https:" || protocol === "http:") void shell.openExternal(target); } catch {} };
  win.webContents.setWindowOpenHandler(({ url: target }) => { external(target); return { action: "deny" }; });
  win.webContents.on("will-navigate", (event, target) => { if (target !== win.webContents.getURL()) { event.preventDefault(); external(target); } });
}
app.whenReady().then(() => { ipcMain.handle("atlas:invoke", async (_event, channel: string, input?: unknown) => { if (!allow.has(channel)) throw new Error("Operación no permitida."); if (channel === "system:status") return systemStatus(); if (channel === "system:processes") { try { return JSON.parse(await powershell("Get-Process | Sort-Object CPU -Descending | Select-Object -First 30 ProcessName,Id,CPU,WorkingSet64 | ConvertTo-Json -Compress")); } catch { return []; } } if (channel === "files:pick") { const picked = await dialog.showOpenDialog({ properties: ["openFile", "multiSelections"] }); return picked.canceled ? [] : picked.filePaths.map((filePath) => path.basename(filePath)); } if (channel === "layout:load") { try { return JSON.parse(await (await import("node:fs/promises")).readFile(layoutPath(), "utf8")); } catch { return null; } } if (channel === "layout:save") { await (await import("node:fs/promises")).writeFile(layoutPath(), JSON.stringify(input)); return true; } if (channel === "atlas:service-status") return serviceStatus(); if (channel === "atlas:chat") return atlasChat(input); if (channel === "atlas:confirm") return atlasConfirm(input); if (channel === "atlas:api") return atlasApi(input); if (channel === "atlas:transcribe") return atlasTranscribe(input); if (channel === "atlas:speak") return atlasSpeak(input); if (channel === "atlas:speaker-status") return atlasSpeakerRequest("GET"); if (channel === "atlas:speaker-delete") return atlasSpeakerRequest("DELETE"); if (channel === "atlas:speaker-enroll") return atlasSpeakerEnroll(input); if (channel === "creative:open-folder") return openCreationsFolder(); return null; }); restrictPermissions(); trustDevCertificate(); if (bundled) backendReady = ensureBundledBackend(); createWindow(); app.on("activate", () => { if (!BrowserWindow.getAllWindows().length) createWindow(); }); }); app.on("will-quit", stopBundledBackend); app.on("window-all-closed", () => { if (process.platform !== "darwin") app.quit(); });
