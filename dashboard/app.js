"use strict";

/* ---------- Config / estado ---------- */
/* Mismo criterio que mobile/app.js: cliente PC-only (Fase 9), pero la API
   sigue siendo la misma — mismo esquema de login/token que la PWA. Claves
   de localStorage separadas para no pisar la sesión del móvil si algún día
   se abren ambos en el mismo navegador. */

// El dashboard se sirve por http:// (127.0.0.1 ya es "contexto seguro" para
// el micrófono sin necesitar HTTPS propio), pero el backend puede estar en
// https:// si hay certificado (ver scripts/generate_dev_cert.py) — no se
// puede asumir que comparten esquema como sí hacía location.protocol acá
// antes (eso rompía el login con "Failed to fetch" apenas el backend pasaba
// a HTTPS-only). Se prueban ambos esquemas al cargar la página.
const API_HOST = location.hostname || "127.0.0.1";
const DEFAULT_API_URL = `https://${API_HOST}:8000`;
let API_URL = localStorage.getItem("atlas_dashboard_api_url") || DEFAULT_API_URL;
let TOKEN = localStorage.getItem("atlas_dashboard_token") || null;
let CONVERSATION_ID = null;

async function detectApiUrl() {
  if (localStorage.getItem("atlas_dashboard_api_url")) return; // el usuario ya eligió una URL a mano
  for (const scheme of ["https", "http"]) {
    const candidate = `${scheme}://${API_HOST}:8000`;
    try {
      const controller = new AbortController();
      const timeout = setTimeout(() => controller.abort(), 1500);
      const res = await fetch(`${candidate}/api/v1/system/health`, { signal: controller.signal });
      clearTimeout(timeout);
      if (res.ok) {
        API_URL = candidate;
        loginApiUrlInput.placeholder = `URL del servidor (auto: ${API_URL})`;
        return;
      }
    } catch {
      /* ese esquema no respondió — probar el siguiente */
    }
  }
}

/* ---------- Fetch autenticado ---------- */

async function api(path, options = {}) {
  const headers = Object.assign({}, options.headers || {});
  if (TOKEN) headers["Authorization"] = `Bearer ${TOKEN}`;
  if (options.body && !(options.body instanceof FormData) && !headers["Content-Type"]) {
    headers["Content-Type"] = "application/json";
  }
  const response = await fetch(`${API_URL}${path}`, { ...options, headers });
  if (response.status === 401) {
    logout();
    throw new Error("Sesión expirada, iniciá sesión de nuevo.");
  }
  if (!response.ok) {
    let detail = response.statusText;
    try {
      detail = (await response.json()).detail || detail;
    } catch {
      /* respuesta sin cuerpo JSON */
    }
    throw new Error(detail);
  }
  const contentType = response.headers.get("content-type") || "";
  return contentType.includes("application/json") ? response.json() : response;
}

/* ---------- Login ---------- */

const loginScreen = document.getElementById("login-screen");
const appScreen = document.getElementById("app-screen");
const loginForm = document.getElementById("login-form");
const loginError = document.getElementById("login-error");
const loginApiUrlInput = document.getElementById("login-api-url");

loginApiUrlInput.value = API_URL === DEFAULT_API_URL ? "" : API_URL;
loginApiUrlInput.placeholder = `URL del servidor (auto: ${DEFAULT_API_URL})`;
// detectApiUrl ajusta API_URL/placeholder según http/https responda de verdad;
// recién después se intenta el auto-login (necesita la URL buena).
const apiUrlReady = detectApiUrl();

loginForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  loginError.textContent = "";

  const password = document.getElementById("login-password").value;
  const customUrl = loginApiUrlInput.value.trim();
  API_URL = customUrl || API_URL;

  try {
    const response = await fetch(`${API_URL}/api/v1/auth/login`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ password }),
    });
    if (!response.ok) throw new Error("Contraseña incorrecta.");
    const body = await response.json();
    TOKEN = body.access_token;
    localStorage.setItem("atlas_dashboard_token", TOKEN);
    localStorage.setItem("atlas_dashboard_api_url", API_URL);
    enterApp();
  } catch (err) {
    loginError.textContent = err.message || "No se pudo conectar al servidor.";
  }
});

function logout() {
  TOKEN = null;
  localStorage.removeItem("atlas_dashboard_token");
  appScreen.classList.add("hidden");
  loginScreen.classList.remove("hidden");
}
document.getElementById("logout-button").addEventListener("click", logout);

function enterApp() {
  loginScreen.classList.add("hidden");
  appScreen.classList.remove("hidden");
  checkConnection();
  loadDevices();
  loadAutomations();
  loadNotifications();
  loadMemory();
  loadActivity();
  pollSystemStatus();
}

async function checkConnection() {
  const statusEl = document.getElementById("connection-status");
  try {
    const response = await fetch(`${API_URL}/api/v1/system/health`);
    statusEl.textContent = response.ok ? "conectado" : "sin conexión";
  } catch {
    statusEl.textContent = "sin conexión";
  }
}

/* Si el backend tiene el login desactivado (AUTH_ENABLED=false), acepta
   cualquier contraseña: se entra solo sin mostrar el formulario. Si no, el
   login falla y queda la pantalla de contraseña como siempre. */
async function tryAutoLogin() {
  await apiUrlReady;
  try {
    const response = await fetch(`${API_URL}/api/v1/auth/login`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ password: "" }),
    });
    if (!response.ok) return;
    TOKEN = (await response.json()).access_token;
    localStorage.setItem("atlas_dashboard_token", TOKEN);
    enterApp();
  } catch {
    /* backend inalcanzable — queda la pantalla de login */
  }
}

if (TOKEN) enterApp();
else tryAutoLogin();

/* ---------- Navegación por sidebar ---------- */

document.querySelectorAll(".nav-button").forEach((btn) => {
  btn.addEventListener("click", () => {
    document.querySelectorAll(".nav-button").forEach((b) => b.classList.remove("active"));
    document.querySelectorAll(".view").forEach((v) => v.classList.remove("active"));
    btn.classList.add("active");
    document.getElementById(`view-${btn.dataset.view}`).classList.add("active");
  });
});

/* ---------- Chat ---------- */

const chatLog = document.getElementById("chat-log");
const chatForm = document.getElementById("chat-form");
const chatInput = document.getElementById("chat-input");

function appendBubble(who, text) {
  const bubble = document.createElement("div");
  bubble.className = `chat-bubble ${who === "atlas" ? "atlas" : "user"}`;
  bubble.textContent = text;
  chatLog.appendChild(bubble);
  chatLog.scrollTop = chatLog.scrollHeight;
  return bubble;
}

/* Imágenes que devuelven las tools (mapa de nubes, cámara pública…). */
function appendImages(bubble, images) {
  (images || []).forEach((image) => {
    const img = document.createElement("img");
    img.className = "chat-image";
    img.alt = "Imagen enviada por ATLAS";
    img.src = `data:${image.mime_type};base64,${image.data}`;
    img.addEventListener("click", () => window.open(img.src, "_blank", "noopener"));
    bubble.appendChild(img);
  });
  chatLog.scrollTop = chatLog.scrollHeight;
}

const TOOL_LABELS = {
  query_world: "Consultando el mundo", show_world_view: "Moviendo el globo",
  web_search: "Buscando en internet", read_web_page: "Leyendo la página",
  search_documents: "Buscando en tus documentos", search_files: "Buscando archivos",
  read_clipboard: "Leyendo el portapapeles", daily_briefing: "Armando el briefing",
  create_reminder: "Creando el recordatorio", create_world_alert: "Creando la alerta",
  analyze_screenshot: "Mirando la pantalla", get_system_info: "Revisando el sistema",
};

/* Chat por Server-Sent Events: onEvent recibe "delta" (texto parcial) y
   "tool" (herramienta en uso); devuelve el evento final, igual a la respuesta
   de POST /chat. Se usa fetch y no EventSource porque hay que mandar POST y
   el header Authorization. */
async function streamChat(message, onEvent) {
  const response = await fetch(`${API_URL}/api/v1/chat/stream`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...(TOKEN ? { Authorization: `Bearer ${TOKEN}` } : {}) },
    body: JSON.stringify({ message, conversation_id: CONVERSATION_ID }),
  });
  if (response.status === 401) {
    logout();
    throw new Error("Sesión expirada, iniciá sesión de nuevo.");
  }
  if (response.status === 404 || !response.body) {
    // Backend sin streaming: se usa el chat de siempre.
    return api("/api/v1/chat", {
      method: "POST",
      body: JSON.stringify({ message, conversation_id: CONVERSATION_ID }),
    });
  }
  if (!response.ok) throw new Error(response.statusText || `error ${response.status}`);

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let final = null;
  for (;;) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    let cut;
    while ((cut = buffer.indexOf("\n\n")) >= 0) {
      const block = buffer.slice(0, cut);
      buffer = buffer.slice(cut + 2);
      for (const line of block.split("\n")) {
        if (!line.startsWith("data: ")) continue;
        const event = JSON.parse(line.slice(6));
        if (event.type === "done") final = event;
        else onEvent(event);
      }
    }
  }
  if (!final) throw new Error("La respuesta se cortó antes de terminar.");
  return final;
}

async function sendChat(message) {
  appendBubble("user", message);
  const bubble = appendBubble("atlas", "…");
  bubble.classList.add("pending");
  const speech = createSpeechStream();
  let streamed = "";
  try {
    const result = await streamChat(message, (event) => {
      if (event.type === "delta") {
        streamed += event.text;
        bubble.classList.remove("pending");
        bubble.textContent = streamed;
        speech.push(event.text);
      } else if (event.type === "tool") {
        // Lo dicho antes de usar la herramienta era un preámbulo: la respuesta viene después.
        streamed = "";
        bubble.classList.add("pending");
        bubble.textContent = `${TOOL_LABELS[event.name] || event.name}…`;
      }
      chatLog.scrollTop = chatLog.scrollHeight;
    });
    CONVERSATION_ID = result.conversation_id;
    pollWorldView(); // si la respuesta movió el globo, mostrarlo ya sin esperar al sondeo
    if (result.requires_confirmation) {
      bubble.remove();
      askConfirmation(result.confirmation_id, result.confirmation_description);
    } else {
      bubble.textContent = result.reply || "(sin respuesta)";
      appendImages(bubble, result.images);
      speech.finish(result.reply);
    }
  } catch (err) {
    bubble.textContent = `(error: ${err.message})`;
  }
  bubble.classList.remove("pending");
}

chatForm.addEventListener("submit", (event) => {
  event.preventDefault();
  const message = chatInput.value.trim();
  if (!message) return;
  chatInput.value = "";
  sendChat(message);
});

/* ---------- Confirmación de acciones riesgosas ---------- */

const confirmDialog = document.getElementById("confirm-dialog");
const confirmMessage = document.getElementById("confirm-message");
let pendingConfirmationId = null;

function askConfirmation(confirmationId, description) {
  pendingConfirmationId = confirmationId;
  confirmMessage.textContent = description || "¿Confirmar esta acción?";
  confirmDialog.classList.remove("hidden");
}

async function resolveConfirmation(approve) {
  confirmDialog.classList.add("hidden");
  if (!pendingConfirmationId) return;
  try {
    const result = await api("/api/v1/chat/confirm", {
      method: "POST",
      body: JSON.stringify({ confirmation_id: pendingConfirmationId, approve }),
    });
    appendImages(appendBubble("atlas", result.reply), result.images);
    pollWorldView();
  } catch (err) {
    appendBubble("atlas", `(error: ${err.message})`);
  }
  pendingConfirmationId = null;
}
document.getElementById("confirm-approve").addEventListener("click", () => resolveConfirmation(true));
document.getElementById("confirm-cancel").addEventListener("click", () => resolveConfirmation(false));

/* ---------- Dispositivos ---------- */

const SAFE_ACTIONS = { LIGHT: "turn", SWITCH: "turn", PLUG: "turn", FAN: "turn", TV: "turn" };

function renderDeviceCard(device) {
  const card = document.createElement("div");
  card.className = "card";
  const isOn = device.state === "on" || device.state === "unlocked";
  const canToggle = device.type in SAFE_ACTIONS;
  card.innerHTML = `
    <div class="card-info">
      <span class="card-title">${device.name}</span>
      <span class="card-subtitle">${device.room || "sin habitación"} · ${device.type} · ${device.state}</span>
    </div>
    ${canToggle ? `<button class="${isOn ? "" : "off"}">${isOn ? "Apagar" : "Encender"}</button>` : ""}
  `;
  if (canToggle) {
    card.querySelector("button").addEventListener("click", () => {
      const action = isOn ? "apaga" : "enciende";
      sendChat(`${action} ${device.name}`);
    });
  }
  return card;
}

async function loadDevices() {
  const list = document.getElementById("device-list");
  const homeList = document.getElementById("home-device-list");
  try {
    const devices = await api("/api/v1/devices");
    if (!devices.length) {
      list.innerHTML = '<div class="empty-state">No hay dispositivos. Configurá SMART_HOME_PROVIDER en el backend.</div>';
      homeList.innerHTML = '<div class="empty-state">Sin dispositivos.</div>';
      return;
    }
    list.innerHTML = "";
    homeList.innerHTML = "";
    devices.forEach((device) => {
      list.appendChild(renderDeviceCard(device));
      if (homeList.children.length < 4) homeList.appendChild(renderDeviceCard(device));
    });
  } catch (err) {
    list.innerHTML = `<div class="empty-state">Error cargando dispositivos: ${err.message}</div>`;
    homeList.innerHTML = "";
  }
}
document.getElementById("refresh-devices").addEventListener("click", loadDevices);

/* ---------- Automatizaciones ---------- */

async function loadAutomations() {
  const list = document.getElementById("automation-list");
  try {
    const routines = await api("/api/v1/automations");
    if (!routines.length) {
      list.innerHTML = '<div class="empty-state">No hay rutinas creadas todavía.</div>';
      return;
    }
    list.innerHTML = "";
    routines.forEach((routine) => {
      const card = document.createElement("div");
      card.className = "card";
      card.innerHTML = `
        <div class="card-info">
          <span class="card-title">${routine.name}</span>
          <span class="card-subtitle">${routine.actions.length} acción(es) · ${routine.triggers.length} trigger(s)</span>
        </div>
        <button>Ejecutar</button>
      `;
      card.querySelector("button").addEventListener("click", async () => {
        try {
          const result = await api(`/api/v1/automations/${routine.id}/run`, { method: "POST" });
          appendBubble("atlas", `Rutina '${result.routine_name}' ejecutada.`);
        } catch (err) {
          appendBubble("atlas", `(error ejecutando la rutina: ${err.message})`);
        }
      });
      list.appendChild(card);
    });
  } catch (err) {
    list.innerHTML = `<div class="empty-state">Error cargando rutinas: ${err.message}</div>`;
  }
}
document.getElementById("refresh-automations").addEventListener("click", loadAutomations);

/* ---------- Notificaciones ---------- */

/* El backend guarda las fechas en UTC pero algunas llegan sin zona: sin la
   "Z" el navegador las tomaría como hora local. */
function parseServerDate(value) {
  return new Date(/[zZ]|[+-]\d\d:\d\d$/.test(value) ? value : `${value}Z`);
}

async function loadNotifications() {
  const list = document.getElementById("notification-list");
  try {
    const notifications = await api("/api/v1/notifications");
    if (!notifications.length) {
      list.innerHTML = '<div class="empty-state">Sin notificaciones.</div>';
      return;
    }
    list.innerHTML = "";
    notifications.forEach((n) => {
      const card = document.createElement("div");
      card.className = "card";
      // El mensaje puede traer texto de fuentes externas (alertas del mundo):
      // va por textContent, nunca como HTML.
      card.innerHTML = `
        <div class="card-info">
          <span class="card-title"></span>
          <span class="badge ${n.read ? "" : "unread"}">${n.read ? "leída" : "nueva"} · ${parseServerDate(n.created_at).toLocaleString()}</span>
        </div>
        ${n.read ? "" : '<button class="secondary">Marcar leída</button>'}
      `;
      card.querySelector(".card-title").textContent = n.message;
      if (!n.read) {
        card.querySelector("button").addEventListener("click", async () => {
          await api(`/api/v1/notifications/${n.id}/read`, { method: "PATCH" });
          loadNotifications();
        });
      }
      list.appendChild(card);
    });
  } catch (err) {
    list.innerHTML = `<div class="empty-state">Error cargando notificaciones: ${err.message}</div>`;
  }
}
document.getElementById("refresh-notifications").addEventListener("click", loadNotifications);

/* ---------- Memoria ---------- */

async function loadMemory() {
  const list = document.getElementById("memory-list");
  try {
    const entries = await api("/api/v1/memory");
    if (!entries.length) {
      list.innerHTML = '<div class="empty-state">ATLAS todavía no tiene nada guardado sobre vos.</div>';
      return;
    }
    list.innerHTML = "";
    entries.forEach((m) => {
      const card = document.createElement("div");
      card.className = "card";
      card.innerHTML = `
        <div class="card-info">
          <span class="card-title">${m.content}</span>
          <span class="badge">${m.category}</span>
        </div>
        <button class="secondary">Olvidar</button>
      `;
      card.querySelector("button").addEventListener("click", async () => {
        await api(`/api/v1/memory/${m.id}`, { method: "DELETE" });
        loadMemory();
      });
      list.appendChild(card);
    });
  } catch (err) {
    list.innerHTML = `<div class="empty-state">Error cargando memoria: ${err.message}</div>`;
  }
}
document.getElementById("refresh-memory").addEventListener("click", loadMemory);

/* ---------- Actividad (AuditLog, Fase 9: nunca antes expuesto vía API) ---------- */

function renderActivityCard(entry) {
  const card = document.createElement("div");
  card.className = "card";
  card.innerHTML = `
    <div class="card-info">
      <span class="card-title">${entry.tool_name}</span>
      <span class="card-subtitle">${entry.result_summary || ""}</span>
    </div>
    <span class="badge ${entry.success ? "" : "fail"}">${entry.success ? entry.risk_level : "falló"} · ${new Date(entry.created_at).toLocaleTimeString()}</span>
  `;
  return card;
}

async function loadActivity() {
  const list = document.getElementById("activity-list");
  const homeList = document.getElementById("home-activity-list");
  try {
    const entries = await api("/api/v1/system/activity?limit=30");
    if (!entries.length) {
      list.innerHTML = '<div class="empty-state">Todavía no hay actividad registrada.</div>';
      homeList.innerHTML = '<div class="empty-state">Sin actividad todavía.</div>';
      return;
    }
    list.innerHTML = "";
    homeList.innerHTML = "";
    entries.forEach((entry) => {
      list.appendChild(renderActivityCard(entry));
      if (homeList.children.length < 5) homeList.appendChild(renderActivityCard(entry));
    });
  } catch (err) {
    list.innerHTML = `<div class="empty-state">Error cargando actividad: ${err.message}</div>`;
    homeList.innerHTML = "";
  }
}
document.getElementById("refresh-activity").addEventListener("click", loadActivity);

/* ---------- Anillos de CPU/RAM/Disco (datos reales, sondeados) ---------- */

function setRing(id, valueId, percent) {
  const ring = document.getElementById(id);
  const value = document.getElementById(valueId);
  const pct = Math.max(0, Math.min(100, Math.round(percent)));
  ring.style.setProperty("--pct", pct);
  value.textContent = `${pct}%`;
}

async function pollSystemStatus() {
  try {
    const status = await api("/api/v1/system/status");
    setRing("ring-cpu", "ring-cpu-value", status.cpu_percent);
    setRing("ring-ram", "ring-ram-value", status.ram_percent);
    setRing("ring-disk", "ring-disk-value", status.disk_percent);
  } catch {
    /* el próximo sondeo lo reintenta; no vale la pena mostrar error acá */
  }
  if (TOKEN) setTimeout(pollSystemStatus, 4000);
}

/* ---------- Orbe de voz: grabación + visualizador real (Web Audio API) ---------- */
/* Nada de animación falsa: el pulso del orbe sale de datos reales del
   micrófono (AnalyserNode.getByteTimeDomainData), igual mientras se graba
   como mientras se reproduce la respuesta hablada de ATLAS. */

const orbButton = document.getElementById("orb-button");
const orbCanvas = document.getElementById("orb-canvas");
const orbCtx = orbCanvas.getContext("2d");
const orbStatus = document.getElementById("orb-status");
const orbIcon = document.getElementById("orb-icon");

let orbAudioCtx = null;
let orbAnalyser = null;
let orbDataArray = null;
let orbRafId = null;
let orbStream = null;
let mediaRecorder = null;
let audioChunks = [];
let orbRecording = false;

function drawOrbIdle() {
  orbCtx.clearRect(0, 0, orbCanvas.width, orbCanvas.height);
}

function drawWaveform(dataArray) {
  const w = orbCanvas.width;
  const h = orbCanvas.height;
  const cx = w / 2;
  const cy = h / 2;
  const baseRadius = 78;

  orbCtx.clearRect(0, 0, w, h);
  orbCtx.beginPath();
  const step = (Math.PI * 2) / dataArray.length;
  for (let i = 0; i < dataArray.length; i++) {
    const amplitude = (dataArray[i] - 128) / 128; // -1..1, muestra real de la onda
    const radius = baseRadius + amplitude * 34;
    const angle = i * step;
    const x = cx + Math.cos(angle) * radius;
    const y = cy + Math.sin(angle) * radius;
    if (i === 0) orbCtx.moveTo(x, y);
    else orbCtx.lineTo(x, y);
  }
  orbCtx.closePath();
  orbCtx.strokeStyle = "#4fc3f7";
  orbCtx.lineWidth = 2;
  orbCtx.stroke();
  orbCtx.fillStyle = "rgba(79, 195, 247, 0.12)";
  orbCtx.fill();
}

function drawOrbFrame() {
  if (!orbAnalyser) return;
  orbRafId = requestAnimationFrame(drawOrbFrame);
  orbAnalyser.getByteTimeDomainData(orbDataArray);
  drawWaveform(orbDataArray);
}

async function startOrbRecording() {
  try {
    orbStream = await navigator.mediaDevices.getUserMedia({ audio: true });
  } catch (err) {
    orbStatus.textContent = `No pude acceder al micrófono: ${err.message}`;
    return;
  }

  orbAudioCtx = new (window.AudioContext || window.webkitAudioContext)();
  const source = orbAudioCtx.createMediaStreamSource(orbStream);
  orbAnalyser = orbAudioCtx.createAnalyser();
  orbAnalyser.fftSize = 128;
  orbDataArray = new Uint8Array(orbAnalyser.frequencyBinCount);
  source.connect(orbAnalyser); // nunca a destination: no queremos escuchar nuestro propio mic

  audioChunks = [];
  mediaRecorder = new MediaRecorder(orbStream);
  mediaRecorder.ondataavailable = (e) => audioChunks.push(e.data);
  mediaRecorder.onstop = async () => {
    const blob = new Blob(audioChunks, { type: mediaRecorder.mimeType || "audio/webm" });
    await transcribeAndSend(blob);
  };
  mediaRecorder.start();

  orbRecording = true;
  orbButton.classList.add("listening");
  orbIcon.textContent = "⏹️";
  orbStatus.textContent = "Escuchando… tocá de nuevo para enviar";
  drawOrbFrame();
}

function stopOrbRecording() {
  orbRecording = false;
  orbButton.classList.remove("listening");
  orbIcon.textContent = "🎙️";
  orbStatus.textContent = "Procesando…";

  if (orbRafId) cancelAnimationFrame(orbRafId);
  orbRafId = null;
  drawOrbIdle();

  if (mediaRecorder && mediaRecorder.state === "recording") mediaRecorder.stop();
  if (orbStream) {
    orbStream.getTracks().forEach((t) => t.stop());
    orbStream = null;
  }
  if (orbAudioCtx) {
    orbAudioCtx.close().catch(() => {});
    orbAudioCtx = null;
  }
  orbAnalyser = null;
}

async function transcribeAndSend(blob) {
  const form = new FormData();
  form.append("audio", blob, "audio.webm");
  try {
    const result = await api("/api/v1/voice/transcribe", { method: "POST", body: form });
    orbStatus.textContent = "Tocá el orbe para hablar";
    if (result.text && result.text.trim()) {
      document.querySelector('.nav-button[data-view="chat"]').click();
      await sendChat(result.text);
    }
  } catch (err) {
    orbStatus.textContent = "Tocá el orbe para hablar";
    appendBubble("atlas", `(error transcribiendo: ${err.message})`);
  }
}

orbButton.addEventListener("click", () => {
  if (orbRecording) stopOrbRecording();
  else startOrbRecording();
});

/* ---------- Voz de ATLAS: reproducción con el mismo orbe/visualizador ---------- */
/* Mismo criterio que la grabación: nada de animación decorativa — el
   visualizador lee el audio real de la respuesta mientras suena, con su
   propio AudioContext (el de grabación ya se cerró para entonces). */

/* La voz se reproduce en cola: cada fragmento se pide al backend apenas se
   conoce (en paralelo) pero suena en orden, sin pisarse. */
let speechChain = Promise.resolve();
const SPEECH_TIMEOUT_MS = 90000;

function playAndWait(audio) {
  return new Promise((resolve) => {
    if (orbRecording) return resolve(); // playWithVisualizer no reproduce mientras se graba
    const timer = setTimeout(resolve, SPEECH_TIMEOUT_MS); // por si el navegador bloquea el audio
    const done = () => {
      clearTimeout(timer);
      resolve();
    };
    audio.addEventListener("ended", done, { once: true });
    audio.addEventListener("error", done, { once: true });
    audio.addEventListener("pause", done, { once: true });
    playWithVisualizer(audio);
  });
}

function speak(text) {
  const clean = (text || "").trim();
  if (!clean) return;
  const audioReady = api("/api/v1/voice/speak", { method: "POST", body: JSON.stringify({ text: clean }) })
    .then((response) => response.blob())
    .catch(() => null); // la respuesta de texto ya se mostró; el audio es un extra
  speechChain = speechChain.then(async () => {
    const blob = await audioReady;
    if (blob && blob.size) await playAndWait(new Audio(URL.createObjectURL(blob)));
  });
}

/* Lee en voz alta una respuesta mientras llega: corta en finales de frase
   para empezar a hablar antes de que el modelo termine de escribir. */
const SPEECH_MIN_CHARS = 40;
function createSpeechStream() {
  let buffer = "";
  let spoke = false;
  return {
    push(text) {
      buffer += text;
      const ends = [...buffer.matchAll(/[.!?…](?=\s)|\n/g)];
      const last = ends[ends.length - 1];
      if (!last || last.index + 1 < SPEECH_MIN_CHARS) return;
      speak(buffer.slice(0, last.index + 1));
      buffer = buffer.slice(last.index + 1);
      spoke = true;
    },
    finish(reply) {
      if (buffer.trim()) speak(buffer);
      else if (!spoke) speak(reply);
      buffer = "";
    },
  };
}

function playWithVisualizer(audio) {
  if (orbRecording) return; // no pisar una grabación en curso
  const playCtx = new (window.AudioContext || window.webkitAudioContext)();
  const source = playCtx.createMediaElementSource(audio);
  const analyser = playCtx.createAnalyser();
  analyser.fftSize = 128;
  const dataArray = new Uint8Array(analyser.frequencyBinCount);
  source.connect(analyser);
  analyser.connect(playCtx.destination); // a diferencia del mic, esto sí debe sonar

  orbButton.classList.add("listening");
  orbIcon.textContent = "🔊";
  orbStatus.textContent = "ATLAS está hablando…";

  let rafId;
  const finish = () => {
    if (rafId) cancelAnimationFrame(rafId);
    orbButton.classList.remove("listening");
    orbIcon.textContent = "🎙️";
    orbStatus.textContent = "Tocá el orbe para hablar";
    drawOrbIdle();
    playCtx.close().catch(() => {});
  };

  const draw = () => {
    if (audio.paused || audio.ended) {
      finish();
      return;
    }
    rafId = requestAnimationFrame(draw);
    analyser.getByteTimeDomainData(dataArray);
    drawWaveform(dataArray);
  };

  audio.addEventListener("ended", finish);
  audio.play().then(draw).catch(finish);
}

/* ---------- Productividad y preferencias de la interfaz ---------- */
const VIEW_LABELS = {
  home: ["Inicio", "CENTRO DE CONTROL"], chat: ["Chat", "CONVERSACIÓN CON ATLAS"],
  devices: ["Dispositivos", "HOGAR CONECTADO"], automations: ["Rutinas", "AUTOMATIZACIÓN"],
  notifications: ["Notificaciones", "BANDEJA DE AVISOS"], memory: ["Memoria", "CONTEXTO PERSONAL"],
  activity: ["Actividad", "REGISTRO DEL SISTEMA"],
  world: ["Mundo en vivo", "INTELIGENCIA GEOESPACIAL"],
  privacy: ["Privacidad", "QUÉ SALE DE ESTA PC"],
};

function showToast(message, kind = "success") {
  const region = document.getElementById("toast-region");
  if (!region) return;
  const toast = document.createElement("div");
  toast.className = `toast ${kind}`;
  toast.textContent = message;
  region.appendChild(toast);
  window.setTimeout(() => toast.remove(), 3600);
}

function updateViewMeta(view) {
  const [title, eyebrow] = VIEW_LABELS[view] || ["ATLAS", "PANEL DE CONTROL"];
  document.getElementById("view-title").textContent = title;
  document.getElementById("view-eyebrow").textContent = eyebrow;
}

function openView(view) {
  const button = document.querySelector(`.nav-button[data-view="${view}"]`);
  if (button) button.click();
  updateViewMeta(view);
}

document.querySelectorAll(".nav-button").forEach((button) => {
  button.addEventListener("click", () => updateViewMeta(button.dataset.view));
});
document.querySelectorAll("[data-quick-view]").forEach((button) => {
  button.addEventListener("click", () => openView(button.dataset.quickView));
});

document.getElementById("refresh-all").addEventListener("click", async () => {
  await Promise.allSettled([loadDevices(), loadAutomations(), loadNotifications(), loadMemory(), loadActivity(), api("/api/v1/system/status").then((status) => { setRing("ring-cpu", "ring-cpu-value", status.cpu_percent); setRing("ring-ram", "ring-ram-value", status.ram_percent); setRing("ring-disk", "ring-disk-value", status.disk_percent); })]);
  document.getElementById("last-sync").textContent = `Actualizado ${new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}`;
  showToast("Panel actualizado");
});

document.getElementById("device-search").addEventListener("input", (event) => {
  const query = event.target.value.trim().toLocaleLowerCase();
  document.querySelectorAll("#device-list .card").forEach((card) => {
    card.hidden = query.length > 0 && !card.textContent.toLocaleLowerCase().includes(query);
  });
});

const themeToggle = document.getElementById("theme-toggle");
function applyTheme(theme) {
  document.documentElement.dataset.theme = theme;
  localStorage.setItem("atlas_dashboard_theme", theme);
  themeToggle.textContent = theme === "light" ? "☾" : "◐";
  themeToggle.title = theme === "light" ? "Usar tema oscuro" : "Usar tema claro";
}
applyTheme(localStorage.getItem("atlas_dashboard_theme") || (matchMedia("(prefers-color-scheme: light)").matches ? "light" : "dark"));
themeToggle.addEventListener("click", () => applyTheme(document.documentElement.dataset.theme === "light" ? "dark" : "light"));

window.addEventListener("keydown", (event) => {
  if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "k") {
    event.preventDefault();
    openView("chat");
    chatInput.focus();
  }
  if (event.key === "Escape" && !confirmDialog.classList.contains("hidden")) resolveConfirmation(false);
});

const originalCheckConnection = checkConnection;
checkConnection = async function enhancedConnectionCheck() {
  await originalCheckConnection();
  const connected = document.getElementById("connection-status").textContent === "conectado";
  document.getElementById("last-sync").textContent = connected
    ? `En línea · ${new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}`
    : "Sin conexión";
};
/* ---------- Gods Eye View: consola geoespacial integrada ---------- */
const GODS_EYE_URL = localStorage.getItem("atlas_gods_eye_url") || "http://127.0.0.1:4173";
const worldFrame = document.getElementById("world-frame");
const worldEmpty = document.getElementById("world-empty");
const worldStatus = document.getElementById("world-status");
const GODS_EYE_ORIGIN = new URL(GODS_EYE_URL).origin;
let worldLoaded = false;
let worldReady = false; // el iframe ya avisó que puede recibir vistas (gev:ready)
let pendingWorldView = null; // vista pedida por ATLAS, a la espera de que el iframe esté listo
let lastWorldViewId; // undefined hasta el primer sondeo

async function loadWorldView(force = false) {
  worldStatus.className = "world-status";
  worldStatus.textContent = "Comprobando servicio…";
  try {
    await fetch(GODS_EYE_URL, { mode: "no-cors", cache: "no-store" });
    worldStatus.className = "world-status online";
    worldStatus.textContent = "● Conectado localmente";
    if (!worldLoaded || force) {
      worldReady = false;
      worldFrame.src = `${GODS_EYE_URL}/?embed=1`;
      worldLoaded = true;
    }
    worldFrame.hidden = false;
    worldEmpty.hidden = true;
  } catch {
    worldStatus.className = "world-status offline";
    worldStatus.textContent = "● Servicio no iniciado";
    worldFrame.hidden = true;
    worldEmpty.hidden = false;
  }
}

document.querySelector('.nav-button[data-view="world"]').addEventListener("click", () => loadWorldView());
document.getElementById("world-reload").addEventListener("click", () => loadWorldView(true));
document.getElementById("world-open").addEventListener("click", () => window.open(GODS_EYE_URL, "_blank", "noopener"));

/* ATLAS maneja el globo: las tools show_world_view / query_world dejan una
   vista en el backend y acá se la pasamos al iframe con el protocolo de
   embebido de Gods Eye View (gev:view). Se sondea en vez de leerla de la
   respuesta del chat para que también funcione con pedidos hechos por voz
   desde el cliente de escritorio o el móvil. */
const WORLD_VIEW_RETRIES = 3;
const WORLD_VIEW_RETRY_MS = 1500;
let sentWorldView = null; // última vista enviada al iframe, por si hay que reintentarla

function sendWorldView() {
  sentWorldView.attempts += 1;
  const { id, view } = sentWorldView;
  worldFrame.contentWindow.postMessage({ type: "gev:view", id, view }, GODS_EYE_ORIGIN);
}

function flushWorldView() {
  if (!worldReady || !pendingWorldView) return;
  sentWorldView = { id: pendingWorldView.id, view: pendingWorldView.view, attempts: 0 };
  pendingWorldView = null;
  sendWorldView();
}

window.addEventListener("message", (event) => {
  if (event.source !== worldFrame.contentWindow || event.origin !== GODS_EYE_ORIGIN) return;
  if (event.data?.type === "gev:ready") {
    worldReady = true;
    flushWorldView();
  } else if (event.data?.type === "gev:view-applied" && !event.data.ok) {
    const failed = (event.data.steps || []).filter((step) => !step.ok).map((step) => step.step);
    // Recién cargado, el globo todavía hace su propio vuelo inicial y cancela
    // el nuestro: el paso "camera" falla y queda mirando otro lugar. Se reintenta.
    const current = sentWorldView && sentWorldView.id === event.data.id;
    if (current && failed.includes("camera") && sentWorldView.attempts < WORLD_VIEW_RETRIES) {
      setTimeout(() => {
        if (sentWorldView && sentWorldView.id === event.data.id && worldReady) sendWorldView();
      }, WORLD_VIEW_RETRY_MS);
      return;
    }
    showToast(`Gods Eye View no pudo aplicar: ${failed.join(", ") || event.data.error || "la vista"}`, "error");
  }
});

async function pollWorldView() {
  try {
    const update = await api("/api/v1/world/view");
    if (lastWorldViewId === undefined) {
      lastWorldViewId = update.id; // al abrir el dashboard no se repite una vista vieja
    } else if (update.id && update.id !== lastWorldViewId) {
      lastWorldViewId = update.id;
      pendingWorldView = update;
      openView("world");
      flushWorldView();
      if (update.summary) showToast(update.summary);
    }
  } catch {
    /* el próximo sondeo lo reintenta */
  }
}
setInterval(() => {
  if (TOKEN) pollWorldView();
}, 2500);
if (TOKEN) pollWorldView();

/* ---------- Avisos: alertas del mundo, recordatorios y briefing ---------- */
/* El backend los deja como notificaciones; acá se sondean para mostrarlos (y
   leerlos en voz alta) apenas aparecen, sin tener que abrir la bandeja. */
const speakNotificationsToggle = document.getElementById("speak-notifications");
speakNotificationsToggle.checked = localStorage.getItem("atlas_dashboard_speak_notifications") !== "0";
speakNotificationsToggle.addEventListener("change", () => {
  localStorage.setItem("atlas_dashboard_speak_notifications", speakNotificationsToggle.checked ? "1" : "0");
});

let knownNotificationIds = null; // null hasta el primer sondeo: lo que ya había no se anuncia

function setUnreadCount(count) {
  const button = document.querySelector('.nav-button[data-view="notifications"]');
  let badge = button.querySelector(".nav-count");
  if (!count) {
    if (badge) badge.remove();
    return;
  }
  if (!badge) {
    badge = document.createElement("span");
    badge.className = "nav-count";
    button.appendChild(badge);
  }
  badge.textContent = count > 99 ? "99+" : String(count);
}

async function pollNotifications() {
  let unread;
  try {
    unread = await api("/api/v1/notifications?unread_only=true");
  } catch {
    return; // el próximo sondeo lo reintenta
  }
  setUnreadCount(unread.length);
  const fresh = knownNotificationIds ? unread.filter((n) => !knownNotificationIds.has(n.id)) : [];
  knownNotificationIds = new Set([...(knownNotificationIds || []), ...unread.map((n) => n.id)]);
  if (!fresh.length) return;
  fresh.reverse().forEach((n) => {
    showToast(n.message);
    if (speakNotificationsToggle.checked) speak(n.message.replace(/^[^\p{L}\p{N}]+/u, "")); // sin el emoji inicial
  });
  loadNotifications();
  loadReminders(); // un recordatorio que acaba de sonar ya no está pendiente
}
setInterval(() => {
  if (TOKEN) pollNotifications();
}, 5000);
if (TOKEN) pollNotifications();

/* Tarjeta con título, detalle y un botón opcional; todo por textContent. */
function buildCard(title, detail, action) {
  const card = document.createElement("div");
  card.className = "card";
  const info = document.createElement("div");
  info.className = "card-info";
  const titleEl = document.createElement("span");
  titleEl.className = "card-title";
  titleEl.textContent = title;
  const detailEl = document.createElement("span");
  detailEl.className = "badge";
  detailEl.textContent = detail;
  info.append(titleEl, detailEl);
  card.appendChild(info);
  if (action) {
    const button = document.createElement("button");
    button.className = "secondary";
    button.textContent = action.label;
    button.addEventListener("click", action.onClick);
    card.appendChild(button);
  }
  return card;
}

function renderEmpty(list, text) {
  list.replaceChildren();
  const empty = document.createElement("div");
  empty.className = "empty-state";
  empty.textContent = text;
  list.appendChild(empty);
}

async function loadReminders() {
  const list = document.getElementById("reminder-list");
  try {
    const reminders = await api("/api/v1/reminders");
    if (!reminders.length) {
      renderEmpty(list, 'Sin recordatorios. Probá: "recordame sacar la pizza en 20 minutos".');
      return;
    }
    list.replaceChildren(
      ...reminders.map((r) => {
        const repeat = { daily: " · todos los días", weekdays: " · lunes a viernes", weekly: " · cada semana" }[r.repeat] || "";
        return buildCard(r.message, `${parseServerDate(r.due_at).toLocaleString([], { dateStyle: "short", timeStyle: "short" })}${repeat}`, {
          label: "Cancelar",
          onClick: async () => {
            await api(`/api/v1/reminders/${r.id}`, { method: "DELETE" });
            loadReminders();
          },
        });
      })
    );
  } catch (err) {
    renderEmpty(list, `Error cargando recordatorios: ${err.message}`);
  }
}

async function loadWorldAlerts() {
  const list = document.getElementById("world-alert-list");
  try {
    const alerts = await api("/api/v1/world/alerts");
    if (!alerts.length) {
      renderEmpty(list, 'Sin alertas. Probá: "avisame si hay un terremoto mayor a 5 cerca de Chile".');
      return;
    }
    list.replaceChildren(
      ...alerts.map((a) => {
        const checked = a.last_checked_at
          ? `última revisión ${parseServerDate(a.last_checked_at).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}`
          : "todavía sin revisar";
        return buildCard(a.description, `cada ${a.interval_minutes} min · ${checked}`, {
          label: "Borrar",
          onClick: async () => {
            await api(`/api/v1/world/alerts/${a.id}`, { method: "DELETE" });
            loadWorldAlerts();
          },
        });
      })
    );
  } catch (err) {
    renderEmpty(list, `Error cargando alertas: ${err.message}`);
  }
}

/* ---------- Privacidad ---------- */
const PRIVACY_LABELS = { local: "No sale de esta PC", network: "Tu red local", external: "Sale a internet", off: "Sin uso" };

async function loadPrivacy() {
  const list = document.getElementById("privacy-list");
  try {
    const report = await api("/api/v1/system/privacy");
    list.replaceChildren(
      ...report.flows.map((flow) => {
        const card = document.createElement("div");
        card.className = "card privacy-card";
        if (flow.area === "Acceso a ATLAS" && !report.auth_enabled) card.classList.add("privacy-warning");
        const info = document.createElement("div");
        info.className = "card-info";
        const title = document.createElement("span");
        title.className = "card-title";
        title.textContent = flow.area;
        const provider = document.createElement("span");
        provider.className = "privacy-provider";
        provider.textContent = flow.provider;
        const sends = document.createElement("span");
        sends.className = "privacy-sends";
        sends.textContent = flow.sends;
        info.append(title, provider, sends);
        const badge = document.createElement("span");
        badge.className = `badge ${flow.destination}`;
        badge.textContent = PRIVACY_LABELS[flow.destination] || flow.destination;
        card.append(info, badge);
        return card;
      })
    );
  } catch (err) {
    renderEmpty(list, `Error cargando el informe: ${err.message}`);
  }
}

/* Estas listas se cargan al entrar a su vista (y con su botón Actualizar). */
const VIEW_LOADERS = { automations: loadReminders, world: loadWorldAlerts, privacy: loadPrivacy };
Object.entries(VIEW_LOADERS).forEach(([view, load]) => {
  document.querySelector(`.nav-button[data-view="${view}"]`).addEventListener("click", load);
});
document.getElementById("refresh-reminders").addEventListener("click", loadReminders);
document.getElementById("refresh-world-alerts").addEventListener("click", loadWorldAlerts);
document.getElementById("refresh-privacy").addEventListener("click", loadPrivacy);
