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
detectApiUrl(); // ajusta API_URL/placeholder según http/https responda de verdad

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

if (TOKEN) enterApp();

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
}

async function sendChat(message) {
  appendBubble("user", message);
  try {
    const result = await api("/api/v1/chat", {
      method: "POST",
      body: JSON.stringify({ message, conversation_id: CONVERSATION_ID }),
    });
    CONVERSATION_ID = result.conversation_id;
    if (result.requires_confirmation) {
      askConfirmation(result.confirmation_id, result.confirmation_description);
    } else if (result.reply) {
      appendBubble("atlas", result.reply);
      speak(result.reply);
    }
  } catch (err) {
    appendBubble("atlas", `(error: ${err.message})`);
  }
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
    appendBubble("atlas", result.reply);
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
      card.innerHTML = `
        <div class="card-info">
          <span class="card-title">${n.message}</span>
          <span class="badge ${n.read ? "" : "unread"}">${n.read ? "leída" : "nueva"} · ${new Date(n.created_at).toLocaleString()}</span>
        </div>
        ${n.read ? "" : '<button class="secondary">Marcar leída</button>'}
      `;
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

async function speak(text) {
  let response;
  try {
    response = await api("/api/v1/voice/speak", { method: "POST", body: JSON.stringify({ text }) });
  } catch {
    return; // la respuesta de texto ya se mostró; el audio es un extra
  }
  const blob = await response.blob();
  const audio = new Audio(URL.createObjectURL(blob));
  playWithVisualizer(audio);
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
