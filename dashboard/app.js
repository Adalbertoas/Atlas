"use strict";

import { WakeWordEngine } from "/shared/wake-word.js";
import { renderMarkdown } from "/shared/markdown.js";

/* ============================================================
   ATLAS — Dashboard (Fase 11: rediseño)

   Regla del proyecto que se mantiene: todo lo que se muestra sale de
   datos reales de la API. Nada de widgets con datos inventados —
   cuando un dato no existe (ej. la temperatura de CPU en equipos que no
   exponen el sensor), la tarjeta se oculta en vez de mostrar un número
   de mentira.
   ============================================================ */

/* ---------- Config / estado ---------- */
/* El dashboard se sirve por http:// (127.0.0.1 ya es "contexto seguro" para
   el micrófono sin necesitar HTTPS propio), pero el backend puede estar en
   https:// si hay certificado (ver scripts/generate_dev_cert.py) — no se
   puede asumir que comparten esquema como sí hacía location.protocol acá
   antes (eso rompía el login con "Failed to fetch" apenas el backend pasaba
   a HTTPS-only). Se prueban ambos esquemas al cargar la página. */
const API_HOST = location.hostname || "127.0.0.1";
const DEFAULT_API_URL = `https://${API_HOST}:8000`;
let API_URL = localStorage.getItem("atlas_dashboard_api_url") || DEFAULT_API_URL;
let TOKEN = localStorage.getItem("atlas_dashboard_token") || null;
let CONVERSATION_ID = null;

let USER_NAME = "";
let LAN_IP = "";
// Valor de respaldo: el real lo define el backend (ATLAS_WAKE_WORD), para
// que escritorio, dashboard y PWA no puedan quedar con palabras distintas.
let WAKE_WORD = "ali";
let DEVICES = [];
let ROUTINES = [];
const SESSION_START = Date.now();

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
  if (response.status === 204) return null;
  const contentType = response.headers.get("content-type") || "";
  return contentType.includes("application/json") ? response.json() : response;
}

/* Iconos: se referencian del sprite SVG que vive al principio de index.html.
   Nada de emojis ni glifos Unicode — el trazo monocromo hereda currentColor
   y no depende de qué tenga la fuente instalada. */
function icon(name) {
  return `<svg class="i"><use href="#i-${name}"/></svg>`;
}

/* Escapado de HTML: los nombres de dispositivos/rutinas/memorias vienen de
   Home Assistant o de lo que el usuario le dictó a ATLAS — se insertan en
   innerHTML, así que no pueden ir crudos. */
function esc(value) {
  return String(value ?? "").replace(/[&<>"']/g, (c) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c])
  );
}

/* ---------- Login ---------- */

const loginScreen = document.getElementById("login-screen");
const appScreen = document.getElementById("app-screen");
const loginForm = document.getElementById("login-form");
const loginError = document.getElementById("login-error");
const loginApiUrlInput = document.getElementById("login-api-url");

loginApiUrlInput.value = API_URL === DEFAULT_API_URL ? "" : API_URL;
loginApiUrlInput.placeholder = `URL del servidor (auto: ${DEFAULT_API_URL})`;
detectApiUrl();

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
  loadProfile();
  checkConnection();
  loadDevices();
  loadAutomations();
  loadReminders();
  loadNotifications();
  loadMemory();
  loadActivity();
  loadTools();
  renderSettings();
  renderQuickChips();
  pollSystemStatus();
  pollGestureStatus();
  pollNotifications();
  drawIdleVisuals();
}

async function checkConnection() {
  const statusEl = document.getElementById("connection-status");
  const detailEl = document.getElementById("connection-detail");
  const dot = document.getElementById("status-dot");
  try {
    const response = await fetch(`${API_URL}/api/v1/system/health`);
    if (!response.ok) throw new Error();
    const health = await response.json();
    statusEl.textContent = "ATLAS Online";
    detailEl.textContent = `Conectado · IA: ${health.ai_provider}`;
    dot.className = "status-dot online";
  } catch {
    statusEl.textContent = "Sin conexión";
    detailEl.textContent = "No se alcanza el servidor";
    dot.className = "status-dot offline";
  }
  if (TOKEN) setTimeout(checkConnection, 15000);
}

/* ---------- Saludo (nombre configurable + franja horaria) ---------- */

async function loadProfile() {
  try {
    const profile = await api("/api/v1/settings/profile");
    USER_NAME = profile.user_name || "";
    WAKE_WORD = profile.wake_word || WAKE_WORD;
    LAN_IP = profile.lan_ip || "";
  } catch {
    USER_NAME = ""; // sin nombre configurado, saludo genérico
  }
  renderGreeting();
  renderSettings(); // se pinta antes de que llegue el perfil; hay que repintarla
  renderGestureUrl();
}

function renderGreeting() {
  const hour = new Date().getHours();
  let saludo = "Buenas noches";
  if (hour >= 6 && hour < 13) saludo = "Buenos días";
  else if (hour >= 13 && hour < 20) saludo = "Buenas tardes";

  document.getElementById("greeting").textContent = USER_NAME
    ? `${saludo}, ${USER_NAME}`
    : `${saludo}`;
}

/* El arranque automático con sesión guardada NO va acá: enterApp() usa
   constantes declaradas más abajo (QUICK_CHIPS, SAFE_TYPES, wakeEngine…) y
   llamarlo a esta altura las encuentra en la zona muerta temporal —
   "Cannot access 'X' before initialization" y la página queda muerta.
   Se llama al final del archivo, cuando todo está inicializado. */

/* ---------- Navegación ---------- */

function goToView(view) {
  // A diferencia de la PWA, acá la cámara NO se apaga al cambiar de vista:
  // el objetivo es manejar el mouse mientras mirás cualquier pantalla, así
  // que apagarla al salir dejaría la función inservible. Solo la apaga el
  // botón. Para que nunca quede corriendo en silencio, mientras está activa
  // se muestra un indicador fijo (ver #gesture-live-indicator).
  document.querySelectorAll(".nav-button").forEach((b) => b.classList.remove("active"));
  document.querySelectorAll(".view").forEach((v) => v.classList.remove("active"));
  const navButton = document.querySelector(`.nav-button[data-view="${view}"]`);
  if (navButton) navButton.classList.add("active");
  document.getElementById(`view-${view}`).classList.add("active");
}

document.querySelectorAll(".nav-button").forEach((btn) => {
  btn.addEventListener("click", () => goToView(btn.dataset.view));
});
document.querySelectorAll("[data-goto]").forEach((btn) => {
  btn.addEventListener("click", () => goToView(btn.dataset.goto));
});
document.getElementById("top-notifications").addEventListener("click", () => goToView("notifications"));

/* ---------- Chat ---------- */

const chatLog = document.getElementById("chat-log");
const chatForm = document.getElementById("chat-form");
const chatInput = document.getElementById("chat-input");

function appendBubble(who, text) {
  const bubble = document.createElement("div");
  bubble.className = `chat-bubble ${who === "atlas" ? "atlas" : "user"}`;
  // Solo las respuestas de ATLAS vienen en Markdown; lo que escribe el
  // usuario se muestra literal.
  if (who === "atlas") {
    bubble.innerHTML = renderMarkdown(text);
  } else {
    bubble.textContent = text;
  }
  chatLog.appendChild(bubble);
  chatLog.scrollTop = chatLog.scrollHeight;
}

// Burbuja de "escribiendo…" (3 puntos), mismo criterio que Claude/ChatGPT:
// el chat puede tardar varios segundos si el modelo dispara una tool
// (buscar en la web, clima, música) y sin esto parece que se colgó.
function showTyping() {
  const bubble = document.createElement("div");
  bubble.className = "chat-bubble atlas typing";
  bubble.innerHTML = "<span class=\"dot\"></span><span class=\"dot\"></span><span class=\"dot\"></span>";
  chatLog.appendChild(bubble);
  chatLog.scrollTop = chatLog.scrollHeight;
  return bubble;
}

async function sendChat(message, { switchView = false } = {}) {
  if (switchView) goToView("chat");
  appendBubble("user", message);
  const typingBubble = showTyping();
  try {
    const result = await api("/api/v1/chat", {
      method: "POST",
      body: JSON.stringify({ message, conversation_id: CONVERSATION_ID }),
    });
    CONVERSATION_ID = result.conversation_id;
    typingBubble.remove();
    if (result.requires_confirmation) {
      askConfirmation(result.confirmation_id, result.confirmation_description);
    } else if (result.reply) {
      appendBubble("atlas", result.reply);
      speak(result.reply);
    }
    // Una acción del chat pudo cambiar el estado real (encender una luz,
    // crear un recordatorio) — refrescar lo que muestra el dashboard.
    loadDevices();
    loadActivity();
    loadReminders();
  } catch (err) {
    typingBubble.remove();
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

// El campo del hero manda al mismo chat y salta a esa vista.
document.getElementById("hero-form").addEventListener("submit", (event) => {
  event.preventDefault();
  const input = document.getElementById("hero-input");
  const message = input.value.trim();
  if (!message) return;
  input.value = "";
  sendChat(message, { switchView: true });
});

/* ---------- Atajos del hero ---------- */
/* Frases fijas que se mandan al chat: no son "datos" inventados, son
   accesos directos a cosas que ATLAS ya sabe hacer con sus tools. */
const QUICK_CHIPS = [
  { icon: "home", label: "Estado de la casa", prompt: "¿Cómo está la casa? Listá los dispositivos y su estado." },
  { icon: "reminder", label: "Mis recordatorios", prompt: "¿Qué recordatorios tengo pendientes?" },
  { icon: "sun", label: "El clima", prompt: "¿Cómo está el clima hoy?" },
  { icon: "gauge", label: "Estado del equipo", prompt: "¿Cómo está el uso de CPU, RAM y disco?" },
];

function renderQuickChips() {
  const container = document.getElementById("quick-actions");
  container.innerHTML = "";
  QUICK_CHIPS.forEach((chip) => {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "chip";
    button.innerHTML = `${icon(chip.icon)}<span>${esc(chip.label)}</span>`;
    button.addEventListener("click", () => sendChat(chip.prompt, { switchView: true }));
    container.appendChild(button);
  });
}

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
    // Hablar acá también: sin esto, todo lo que pasa por confirmación
    // (abrir una app, mirar la pantalla, tocar un dispositivo) respondía
    // mudo, y parecía que la voz fallaba al azar. En realidad dependía de
    // QUÉ se pedía, no de cuándo.
    if (result.reply) speak(result.reply);
    loadDevices();
    loadActivity();
  } catch (err) {
    appendBubble("atlas", `(error: ${err.message})`);
  }
  pendingConfirmationId = null;
}
document.getElementById("confirm-approve").addEventListener("click", () => resolveConfirmation(true));
document.getElementById("confirm-cancel").addEventListener("click", () => resolveConfirmation(false));

/* ---------- Dispositivos ---------- */

/* Tipos con encendido/apagado seguro directo desde la UI. Cerraduras,
   cámaras, sensores y clima quedan fuera a propósito (misma política de
   riesgo que el backend: esas exigen confirmación explícita vía chat). */
const SAFE_TYPES = ["LIGHT", "SWITCH", "PLUG", "FAN", "TV"];

/* Icono + color por tipo. El color no es decorativo: distingue de un
   vistazo un dispositivo de seguridad (ámbar) de una luz o un sensor. */
const TYPE_STYLE = {
  LIGHT:      { icon: "light", cls: "t-light" },
  SWITCH:     { icon: "switch", cls: "t-switch" },
  PLUG:       { icon: "plug", cls: "t-switch" },
  FAN:        { icon: "fan", cls: "t-switch" },
  TV:         { icon: "tv", cls: "t-switch" },
  LOCK:       { icon: "lock", cls: "t-lock" },
  CAMERA:     { icon: "camera", cls: "t-lock" },
  SENSOR:     { icon: "sensor", cls: "t-sensor" },
  CLIMATE:    { icon: "climate", cls: "t-climate" },
  THERMOSTAT: { icon: "climate", cls: "t-climate" },
};
const DEFAULT_TYPE_STYLE = { icon: "sensor", cls: "t-sensor" };

function typeStyle(type) {
  return TYPE_STYLE[type] || DEFAULT_TYPE_STYLE;
}

function isDeviceOn(device) {
  return device.state === "on" || device.state === "unlocked" || device.state === "playing";
}

/* Solo estos tipos tienen un "encendido/apagado" con sentido. Una cerradura
   o un termostato NO son "apagados" — contarlos como tales (como hacía la
   primera versión de este panel) informa mal. */
function isToggleable(device) {
  return SAFE_TYPES.includes(device.type);
}

function renderDeviceRow(device) {
  const row = document.createElement("div");
  row.className = "mini-row";
  const on = isDeviceOn(device);
  const canToggle = isToggleable(device);
  const style = typeStyle(device.type);

  row.innerHTML = `
    <span class="mini-icon ${style.cls} ${on ? "lit" : ""}">${icon(style.icon)}</span>
    <span class="mini-text">
      <span class="mini-title">${esc(device.name)}</span>
      <span class="mini-sub">${esc(device.room || "Sin sala")}${canToggle ? ` · ${on ? "Encendido" : "Apagado"}` : ""}</span>
    </span>
    ${
      canToggle
        ? `<button type="button" class="switch ${on ? "on" : ""}" title="${on ? "Apagar" : "Encender"}"></button>`
        : `<span class="mini-state">${esc(device.state)}</span>`
    }
  `;

  if (canToggle) {
    row.querySelector(".switch").addEventListener("click", () => {
      sendChat(`${on ? "apagá" : "encendé"} ${device.name}`);
    });
  }
  return row;
}

function renderHomeDevices() {
  const list = document.getElementById("home-device-list");
  const mode = document.querySelector("#device-filter .seg-button.active").dataset.filter;
  list.innerHTML = "";

  if (!DEVICES.length) {
    list.innerHTML = '<div class="empty-state">Sin dispositivos.</div>';
    return;
  }

  if (mode === "all") {
    DEVICES.forEach((d) => list.appendChild(renderDeviceRow(d)));
    return;
  }

  // "Salas" y "Tipos" son la misma agrupación sobre distinta clave.
  const key = mode === "rooms" ? "room" : "type";
  const groups = new Map();
  DEVICES.forEach((device) => {
    const groupName = device[key] || "Sin asignar";
    if (!groups.has(groupName)) groups.set(groupName, []);
    groups.get(groupName).push(device);
  });

  [...groups.entries()]
    .sort((a, b) => a[0].localeCompare(b[0]))
    .forEach(([groupName, devices]) => {
      const label = document.createElement("div");
      label.className = "group-label";
      label.textContent = groupName;
      list.appendChild(label);
      devices.forEach((d) => list.appendChild(renderDeviceRow(d)));
    });
}

document.querySelectorAll("#device-filter .seg-button").forEach((btn) => {
  btn.addEventListener("click", () => {
    document.querySelectorAll("#device-filter .seg-button").forEach((b) => b.classList.remove("active"));
    btn.classList.add("active");
    renderHomeDevices();
  });
});

/* Temperatura ambiente informada por un termostato/sensor real, si hay
   alguno. `capabilities.temperature` lo expone tanto el provider mock como
   Home Assistant (atributos de la entidad). Si no hay, la fila se oculta —
   no se inventa un valor. */
function ambientTemperature() {
  for (const device of DEVICES) {
    if (device.type !== "CLIMATE" && device.type !== "THERMOSTAT" && device.type !== "SENSOR") continue;
    const value = device.capabilities?.temperature ?? device.capabilities?.current_temperature;
    if (value != null && !Number.isNaN(Number(value))) return Number(value);
  }
  return null;
}

function renderHouseState() {
  const total = DEVICES.length;
  // Solo lo que realmente se enciende/apaga entra en el conteo: contar una
  // cerradura cerrada como "apagada" sería informar mal.
  const toggleable = DEVICES.filter(isToggleable);
  const on = toggleable.filter(isDeviceOn).length;
  const off = toggleable.length - on;

  document.getElementById("house-on").textContent = `${on} encendido${on === 1 ? "" : "s"}`;
  document.getElementById("house-off").textContent = `${off} apagado${off === 1 ? "" : "s"}`;
  document.getElementById("house-count").textContent = total
    ? `${total} dispositivo${total === 1 ? "" : "s"} conectado${total === 1 ? "" : "s"}`
    : "Sin dispositivos configurados";

  const locked = DEVICES.filter((d) => d.type === "LOCK" && d.state === "locked").length;
  const unlocked = DEVICES.filter((d) => d.type === "LOCK" && d.state === "unlocked").length;
  const securityRow = document.getElementById("house-security");
  if (locked || unlocked) {
    securityRow.classList.remove("hidden");
    securityRow.querySelector("span:last-child").textContent = unlocked
      ? `${unlocked} sin trabar`
      : `${locked} trabada${locked === 1 ? "" : "s"}`;
    securityRow.querySelector(".dot").className = `dot ${unlocked ? "warn" : "on"}`;
  } else {
    securityRow.classList.add("hidden");
  }

  const temperature = ambientTemperature();
  const tempRow = document.getElementById("house-temp");
  if (temperature != null) {
    tempRow.classList.remove("hidden");
    tempRow.querySelector("span:last-child").textContent = `Ambiente ${temperature} °C`;
  } else {
    tempRow.classList.add("hidden");
  }

  const headline = document.getElementById("house-headline");
  if (!total) {
    headline.textContent = "—";
    headline.className = "house-headline";
  } else if (unlocked) {
    headline.textContent = "Puerta sin trabar";
    headline.className = "house-headline warn";
  } else {
    headline.textContent = "Todo normal";
    headline.className = "house-headline";
  }
}

function renderDeviceListView() {
  const list = document.getElementById("device-list");
  if (!DEVICES.length) {
    list.innerHTML =
      '<div class="empty-state">No hay dispositivos. Configurá SMART_HOME_PROVIDER en el backend.</div>';
    return;
  }
  list.innerHTML = "";
  DEVICES.forEach((device) => {
    const on = isDeviceOn(device);
    const canToggle = SAFE_TYPES.includes(device.type);
    const card = document.createElement("div");
    card.className = "card";
    card.innerHTML = `
      <div class="card-info">
        <span class="card-title">${esc(device.name)}</span>
        <span class="card-subtitle">${esc(device.room || "sin sala")} · ${esc(device.type)} · ${esc(device.state)}</span>
      </div>
      ${canToggle ? `<button type="button" class="${on ? "" : "off"}">${on ? "Apagar" : "Encender"}</button>` : ""}
    `;
    if (canToggle) {
      card.querySelector("button").addEventListener("click", () => {
        sendChat(`${on ? "apagá" : "encendé"} ${device.name}`);
      });
    }
    list.appendChild(card);
  });
}

async function loadDevices() {
  try {
    DEVICES = await api("/api/v1/devices");
  } catch (err) {
    document.getElementById("device-list").innerHTML =
      `<div class="empty-state">Error cargando dispositivos: ${esc(err.message)}</div>`;
    document.getElementById("home-device-list").innerHTML = "";
    return;
  }
  renderDeviceListView();
  renderHomeDevices();
  renderHouseState();
}
document.getElementById("refresh-devices").addEventListener("click", loadDevices);

/* ---------- Automatizaciones / rutinas ---------- */

async function runRoutine(routine) {
  try {
    const result = await api(`/api/v1/automations/${routine.id}/run`, { method: "POST" });
    appendBubble("atlas", `Rutina '${result.routine_name}' ejecutada.`);
    loadDevices();
    loadActivity();
  } catch (err) {
    appendBubble("atlas", `(error ejecutando la rutina: ${err.message})`);
  }
}

/* Icono según palabras del nombre de la rutina, que la escribe el usuario.
   Es cosmético: si no matchea nada cae a un ícono genérico de "ejecutar". */
const ROUTINE_ICONS = [
  [/dormir|noche|descans/i, "moon"],
  [/salir|afuera|fuera|ausen/i, "exit"],
  [/apagar|todo off/i, "power"],
  [/pel[íi]cula|cine|film/i, "tv"],
  [/concentra|foco|estudio/i, "target"],
  [/trabajo|oficina/i, "work"],
  [/despertar|buenos d[íi]as|ma[ñn]ana/i, "sun"],
  [/llegar|casa|bienven/i, "home"],
];

function routineIcon(name) {
  for (const [pattern, iconName] of ROUTINE_ICONS) {
    if (pattern.test(name)) return iconName;
  }
  return "play";
}

function renderRoutineShortcuts() {
  const grid = document.getElementById("routine-shortcuts");
  grid.innerHTML = "";
  if (!ROUTINES.length) {
    grid.innerHTML = '<div class="empty-state">Todavía no creaste rutinas.</div>';
    return;
  }
  ROUTINES.slice(0, 6).forEach((routine) => {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "shortcut";
    button.innerHTML = `<span class="shortcut-icon">${icon(routineIcon(routine.name))}</span><span>${esc(routine.name)}</span>`;
    button.addEventListener("click", () => runRoutine(routine));
    grid.appendChild(button);
  });
}

function renderHomeAutomations() {
  const list = document.getElementById("home-automation-list");
  list.innerHTML = "";
  if (!ROUTINES.length) {
    list.innerHTML = '<div class="empty-state">Sin rutinas.</div>';
    return;
  }
  ROUTINES.forEach((routine) => {
    const row = document.createElement("div");
    row.className = "mini-row";
    const triggerCount = routine.triggers.length;
    row.innerHTML = `
      <span class="mini-icon">${icon(routineIcon(routine.name))}</span>
      <span class="mini-text">
        <span class="mini-title">${esc(routine.name)}</span>
        <span class="mini-sub">${triggerCount ? `${triggerCount} trigger(s)` : "Manual"} · ${routine.actions.length} acción(es)</span>
      </span>
      <button type="button" class="switch on" title="Ejecutar ahora"></button>
    `;
    row.querySelector("button").addEventListener("click", () => runRoutine(routine));
    list.appendChild(row);
  });
}

async function loadAutomations() {
  const list = document.getElementById("automation-list");
  try {
    ROUTINES = await api("/api/v1/automations");
  } catch (err) {
    list.innerHTML = `<div class="empty-state">Error cargando rutinas: ${esc(err.message)}</div>`;
    return;
  }

  if (!ROUTINES.length) {
    list.innerHTML = '<div class="empty-state">No hay rutinas creadas todavía.</div>';
  } else {
    list.innerHTML = "";
    ROUTINES.forEach((routine) => {
      const card = document.createElement("div");
      card.className = "card";
      card.innerHTML = `
        <div class="card-info">
          <span class="card-title">${esc(routine.name)}</span>
          <span class="card-subtitle">${routine.actions.length} acción(es) · ${routine.triggers.length} trigger(s)</span>
        </div>
        <button type="button">Ejecutar</button>
      `;
      card.querySelector("button").addEventListener("click", () => runRoutine(routine));
      list.appendChild(card);
    });
  }
  renderRoutineShortcuts();
  renderHomeAutomations();
}
document.getElementById("refresh-automations").addEventListener("click", loadAutomations);

/* ---------- Recordatorios (Fase 11) ---------- */

function formatDue(iso) {
  const date = new Date(iso);
  const today = new Date();
  const tomorrow = new Date(today.getTime() + 86400000);
  const sameDay = (a, b) => a.toDateString() === b.toDateString();

  const time = date.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
  if (sameDay(date, today)) return `Hoy, ${time}`;
  if (sameDay(date, tomorrow)) return `Mañana, ${time}`;
  return `${date.toLocaleDateString([], { day: "2-digit", month: "short" })}, ${time}`;
}

function renderHomeReminders(reminders) {
  const list = document.getElementById("home-reminder-list");
  const pending = reminders.filter((r) => !r.done).slice(0, 4);
  list.innerHTML = "";

  if (!pending.length) {
    list.innerHTML = '<div class="empty-state">Sin recordatorios pendientes.</div>';
    return;
  }
  pending.forEach((reminder) => {
    const overdue = new Date(reminder.due_at) < new Date();
    const row = document.createElement("div");
    row.className = "mini-row";
    row.innerHTML = `
      <span class="mini-icon ${overdue ? "t-lock" : ""}">${icon(overdue ? "alarm" : "reminder")}</span>
      <span class="mini-text">
        <span class="mini-title">${esc(reminder.text)}</span>
        <span class="mini-sub">${esc(formatDue(reminder.due_at))}</span>
      </span>
    `;
    list.appendChild(row);
  });
}

async function loadReminders() {
  const list = document.getElementById("reminder-list");
  let reminders;
  try {
    reminders = await api("/api/v1/reminders");
  } catch (err) {
    list.innerHTML = `<div class="empty-state">Error cargando recordatorios: ${esc(err.message)}</div>`;
    return;
  }

  renderHomeReminders(reminders);

  if (!reminders.length) {
    list.innerHTML = '<div class="empty-state">No tenés recordatorios. Creá uno arriba, o pedíselo a ATLAS por voz.</div>';
    return;
  }
  list.innerHTML = "";
  reminders.forEach((reminder) => {
    const card = document.createElement("div");
    card.className = "card";
    card.innerHTML = `
      <div class="card-info">
        <span class="card-title">${esc(reminder.text)}</span>
        <span class="badge ${reminder.done ? "done" : ""}">${reminder.done ? "hecho" : esc(formatDue(reminder.due_at))}</span>
      </div>
      <div class="card-actions">
        ${reminder.done ? "" : '<button type="button" data-action="done">Listo</button>'}
        <button type="button" class="secondary" data-action="delete">Borrar</button>
      </div>
    `;
    card.querySelector('[data-action="delete"]').addEventListener("click", async () => {
      await api(`/api/v1/reminders/${reminder.id}`, { method: "DELETE" });
      loadReminders();
    });
    const doneButton = card.querySelector('[data-action="done"]');
    if (doneButton) {
      doneButton.addEventListener("click", async () => {
        await api(`/api/v1/reminders/${reminder.id}/done`, { method: "PATCH" });
        loadReminders();
      });
    }
    list.appendChild(card);
  });
}
document.getElementById("refresh-reminders").addEventListener("click", loadReminders);

document.getElementById("reminder-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const textInput = document.getElementById("reminder-text");
  const dueInput = document.getElementById("reminder-due");
  try {
    await api("/api/v1/reminders", {
      method: "POST",
      body: JSON.stringify({
        text: textInput.value.trim(),
        // datetime-local ya viene en hora local sin zona, que es lo que
        // espera el backend (columnas DateTime naive).
        due_at: dueInput.value,
      }),
    });
    textInput.value = "";
    dueInput.value = "";
    loadReminders();
  } catch (err) {
    alert(`No se pudo crear el recordatorio: ${err.message}`);
  }
});

/* ---------- Notificaciones ---------- */

async function loadNotifications() {
  const list = document.getElementById("notification-list");
  const badge = document.getElementById("nav-notification-badge");
  try {
    const notifications = await api("/api/v1/notifications");

    const unread = notifications.filter((n) => !n.read).length;
    badge.textContent = unread;
    badge.classList.toggle("hidden", unread === 0);

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
          <span class="card-title">${esc(n.message)}</span>
          <span class="badge ${n.read ? "" : "unread"}">${n.read ? "leída" : "nueva"} · ${esc(new Date(n.created_at).toLocaleString())}</span>
        </div>
        ${n.read ? "" : '<button type="button" class="secondary">Marcar leída</button>'}
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
    list.innerHTML = `<div class="empty-state">Error cargando notificaciones: ${esc(err.message)}</div>`;
  }
}
document.getElementById("refresh-notifications").addEventListener("click", loadNotifications);

/* Sondeo de notificaciones: sin esto el badge solo se actualizaba al cargar
   la página, así que un recordatorio que vencía mientras la tenías abierta
   no se veía nunca. El scheduler del backend los emite cada 30s. */

let lastUnreadCount = 0;

async function pollNotifications() {
  try {
    const notifications = await api("/api/v1/notifications");
    const unread = notifications.filter((n) => !n.read);

    // Solo avisa cuando aparece una nueva, no en cada sondeo.
    if (unread.length > lastUnreadCount) {
      const nueva = unread[0];
      showToast(nueva.message);
      // Hablarla también: si estás en otra ventana, el aviso visual no
      // alcanza. Es el punto de que el recordatorio te interrumpa.
      speak(nueva.message);
    }
    lastUnreadCount = unread.length;

    const badge = document.getElementById("nav-notification-badge");
    badge.textContent = unread.length;
    badge.classList.toggle("hidden", unread.length === 0);
  } catch {
    /* el próximo sondeo lo reintenta */
  }
  if (TOKEN) setTimeout(pollNotifications, 20000);
}

function showToast(message) {
  const toast = document.createElement("div");
  toast.className = "toast";
  toast.innerHTML = `${icon("bell")}<span>${esc(message)}</span>`;
  toast.addEventListener("click", () => {
    goToView("notifications");
    toast.remove();
  });
  document.body.appendChild(toast);
  // Se va solo, pero queda en la vista de Notificaciones.
  setTimeout(() => toast.classList.add("leaving"), 7000);
  setTimeout(() => toast.remove(), 7500);
}

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
          <span class="card-title">${esc(m.content)}</span>
          <span class="badge">${esc(m.category)}</span>
        </div>
        <button type="button" class="secondary">Olvidar</button>
      `;
      card.querySelector("button").addEventListener("click", async () => {
        await api(`/api/v1/memory/${m.id}`, { method: "DELETE" });
        loadMemory();
      });
      list.appendChild(card);
    });
  } catch (err) {
    list.innerHTML = `<div class="empty-state">Error cargando memoria: ${esc(err.message)}</div>`;
  }
}
document.getElementById("refresh-memory").addEventListener("click", loadMemory);

/* ---------- Control por gestos (Fase 13) ---------- */
/* Esta PC es la máquina controlada: la cámara vive en el celular. Acá no
   hay nada que capturar — solo se informa el estado del receptor, que el
   backend ahora sí registra (app/gestures/session.py). */

const MOBILE_PWA_PORT = 5173; // el que sirve mobile/serve.py

function renderGestureUrl() {
  const el = document.getElementById("gesture-mobile-url");
  // El esquema lo decide el backend: mobile/serve.py usa HTTPS si existe el
  // certificado de desarrollo, y la cámara del celular lo exige igual.
  const scheme = API_URL.startsWith("https") ? "https" : "http";
  el.textContent = LAN_IP
    ? `${scheme}://${LAN_IP}:${MOBILE_PWA_PORT}`
    : `${scheme}://<IP-de-esta-PC>:${MOBILE_PWA_PORT}`;
}

function formatSince(iso) {
  const seconds = Math.floor((Date.now() - new Date(iso).getTime()) / 1000);
  if (seconds < 60) return `hace ${seconds}s`;
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `hace ${minutes} min`;
  return `hace ${Math.floor(minutes / 60)}h ${minutes % 60}min`;
}

async function pollGestureStatus() {
  try {
    const status = await api("/api/v1/gestures/status");
    const card = document.getElementById("gesture-status-card");
    const dot = document.getElementById("gesture-dot");
    const title = document.getElementById("gesture-status-title");
    const detail = document.getElementById("gesture-status-detail");
    const events = document.getElementById("gesture-events");

    if (status.connected) {
      card.classList.add("active");
      dot.className = "gesture-dot live";
      title.textContent = "Celular conectado";
      detail.textContent = status.connected_since
        ? `Controlando el mouse desde ${formatSince(status.connected_since)}`
        : "Controlando el mouse";
      events.textContent = `${status.events_received} gestos`;
      events.classList.remove("hidden");
    } else {
      card.classList.remove("active");
      dot.className = "gesture-dot";
      title.textContent = "Sin celular conectado";
      detail.textContent = status.events_received
        ? "La última sesión terminó. Volvé a activarlo desde el teléfono."
        : "Abrí la PWA en tu teléfono para empezar";
      events.classList.add("hidden");
    }
  } catch {
    /* el próximo sondeo lo reintenta */
  }
  if (TOKEN) setTimeout(pollGestureStatus, 3000);
}

/* ---------- Gestos con la cámara de esta PC ---------- */
/* Misma técnica que mobile/app.js: la detección corre en el navegador
   (MediaPipe Tasks Vision, único recurso de CDN del proyecto) y por el
   WebSocket solo viajan coordenadas y booleanos — nunca video ni imágenes.
   Acá la cámara y el mouse controlado están en la misma máquina, que es el
   caso normal cuando la PC tiene webcam. */

const MEDIAPIPE_CDN = "https://cdn.jsdelivr.net/npm/@mediapipe/tasks-vision@0.10.14";
const HAND_MODEL_URL =
  "https://storage.googleapis.com/mediapipe-models/hand_landmarker/hand_landmarker/float16/1/hand_landmarker.task";
// Umbrales calibrados en vivo en la PWA — se reutilizan tal cual para no
// tener dos comportamientos distintos según desde dónde se controle.
const PINCH_RATIO = 0.55;   // fracción del tamaño de la mano, no distancia fija
const CURLED_RATIO = 0.9;   // dedo doblado: punta más cerca de la muñeca que el nudillo

const gestureVideo = document.getElementById("gesture-video");
const gestureCanvas = document.getElementById("gesture-canvas");
const gestureCtx = gestureCanvas.getContext("2d");
const gestureCameraStatus = document.getElementById("gesture-camera-status");
const gestureToggle = document.getElementById("gesture-toggle");
const gestureLocalBadge = document.getElementById("gesture-local-badge");
const gestureLiveIndicator = document.getElementById("gesture-live-indicator");
gestureLiveIndicator.addEventListener("click", () => goToView("gestures"));

let gesturesActive = false;
let gesturesStream = null;
let gesturesSocket = null;
let handLandmarker = null;
let gesturesRafId = null;
let scrollPrevY = null; // posición previa del puño, para el delta entre frames

async function loadHandLandmarker() {
  if (handLandmarker) return handLandmarker;
  gestureCameraStatus.textContent = "Cargando modelo de detección de manos…";
  const { HandLandmarker, FilesetResolver } = await import(MEDIAPIPE_CDN);
  const vision = await FilesetResolver.forVisionTasks(`${MEDIAPIPE_CDN}/wasm`);
  handLandmarker = await HandLandmarker.createFromOptions(vision, {
    baseOptions: { modelAssetPath: HAND_MODEL_URL, delegate: "GPU" },
    numHands: 2, // derecha = cursor/clic, izquierda = puño para scroll
    runningMode: "VIDEO",
    // Un puño cerrado es más difícil de reconocer como "mano" que una mano
    // abierta — bajar los umbrales evita que el detector lo descarte.
    minHandDetectionConfidence: 0.3,
    minHandPresenceConfidence: 0.3,
    minTrackingConfidence: 0.3,
  });
  return handLandmarker;
}

async function startGestures() {
  try {
    gesturesStream = await navigator.mediaDevices.getUserMedia({
      video: { facingMode: "user", width: 640, height: 480 },
    });
  } catch (err) {
    gestureCameraStatus.textContent = `No pude acceder a la cámara: ${err.message}`;
    return;
  }

  gestureVideo.srcObject = gesturesStream;
  await gestureVideo.play();
  gestureCanvas.width = gestureVideo.videoWidth || 640;
  gestureCanvas.height = gestureVideo.videoHeight || 480;

  try {
    await loadHandLandmarker();
  } catch (err) {
    gestureCameraStatus.textContent = `No pude cargar el modelo de manos: ${err.message}`;
    stopGestures();
    return;
  }

  const wsUrl = `${API_URL.replace(/^http/, "ws")}/api/v1/gestures/stream`;
  gesturesSocket = new WebSocket(wsUrl);
  gesturesSocket.addEventListener("open", () => {
    // El WebSocket del navegador no manda headers custom: el token va como
    // primer mensaje (ver app/api/v1/gestures.py).
    gesturesSocket.send(JSON.stringify({ token: TOKEN }));
  });
  gesturesSocket.addEventListener("close", () => {
    if (gesturesActive) stopGestures();
  });

  gesturesActive = true;
  gestureToggle.textContent = "Desactivar control por gestos";
  gestureToggle.classList.add("active");
  gestureLocalBadge.textContent = "Activa";
  gestureLocalBadge.classList.add("unread");
  gestureLiveIndicator.classList.remove("hidden");
  gestureCameraStatus.textContent = "Buscando tu mano…";
  detectLoop();
}

function stopGestures() {
  gesturesActive = false;
  if (gesturesRafId) cancelAnimationFrame(gesturesRafId);
  gesturesRafId = null;
  if (gesturesSocket) {
    gesturesSocket.close();
    gesturesSocket = null;
  }
  if (gesturesStream) {
    gesturesStream.getTracks().forEach((t) => t.stop());
    gesturesStream = null;
  }
  scrollPrevY = null;
  gestureCtx.clearRect(0, 0, gestureCanvas.width, gestureCanvas.height);
  gestureCameraStatus.textContent = "Cámara apagada";
  gestureToggle.textContent = "Activar control por gestos";
  gestureToggle.classList.remove("active");
  gestureLocalBadge.textContent = "Apagada";
  gestureLocalBadge.classList.remove("unread");
  gestureLiveIndicator.classList.add("hidden");
}

function detectLoop() {
  if (!gesturesActive) return;
  gesturesRafId = requestAnimationFrame(detectLoop);
  if (!handLandmarker || gestureVideo.readyState < 2) return;

  const result = handLandmarker.detectForVideo(gestureVideo, performance.now());
  gestureCtx.save();
  gestureCtx.clearRect(0, 0, gestureCanvas.width, gestureCanvas.height);
  // Espejado: cámara frontal tipo "selfie" — mover la mano hacia tu derecha
  // real mueve el cursor hacia la derecha.
  gestureCtx.translate(gestureCanvas.width, 0);
  gestureCtx.scale(-1, 1);

  // Cada mano tiene un solo trabajo, así nunca se confunden entre sí.
  let sawScrollHand = false;

  if (result.landmarks && result.landmarks.length > 0) {
    const statusParts = [];
    for (let i = 0; i < result.landmarks.length; i++) {
      const hand = result.landmarks[i];
      gestureCtx.fillStyle = "#22d3ee";
      hand.forEach((point) => {
        gestureCtx.beginPath();
        gestureCtx.arc(point.x * gestureCanvas.width, point.y * gestureCanvas.height, 4, 0, Math.PI * 2);
        gestureCtx.fill();
      });

      // La clasificación de MediaPipe es sobre el frame crudo, sin el
      // espejado que solo aplicamos al dibujar.
      const handedness = result.handedness && result.handedness[i] && result.handedness[i][0];
      const isScrollHand = handedness && handedness.categoryName === "Left";

      const wrist = hand[0];
      const indexTip = hand[8];
      const dist = (a, b) => Math.hypot(a.x - b.x, a.y - b.y);

      if (isScrollHand) {
        sawScrollHand = true;
        const indexCurled = dist(indexTip, wrist) < dist(hand[6], wrist) * CURLED_RATIO;
        const middleCurled = dist(hand[12], wrist) < dist(hand[10], wrist) * CURLED_RATIO;
        const ringCurled = dist(hand[16], wrist) < dist(hand[14], wrist) * CURLED_RATIO;
        const pinkyCurled = dist(hand[20], wrist) < dist(hand[18], wrist) * CURLED_RATIO;
        const fist = indexCurled && middleCurled && ringCurled && pinkyCurled;

        if (fist) {
          // Centro de la palma: más estable que una punta de dedo sola.
          const palmY = (wrist.y + hand[9].y) / 2;
          statusParts.push("Puño: scroll");
          if (scrollPrevY !== null && gesturesSocket && gesturesSocket.readyState === WebSocket.OPEN) {
            gesturesSocket.send(JSON.stringify({ scroll: scrollPrevY - palmY }));
          }
          scrollPrevY = palmY;
        } else {
          scrollPrevY = null;
          statusParts.push("Mano de scroll (cerrá el puño)");
        }
      } else {
        const thumbTip = hand[4];
        const handSize = dist(wrist, hand[9]); // escala con la distancia a la cámara
        const pinching = dist(indexTip, thumbTip) < handSize * PINCH_RATIO;
        // El cursor sigue el NUDILLO del índice (landmark 5), no la punta: la
        // punta se mueve hacia el pulgar al pellizcar y desplazaba el cursor
        // justo al querer hacer clic con la mano quieta.
        const cursorPoint = hand[5];
        statusParts.push(pinching ? "Pellizco (clic)" : "Cursor");
        if (gesturesSocket && gesturesSocket.readyState === WebSocket.OPEN) {
          gesturesSocket.send(
            JSON.stringify({ x: 1 - cursorPoint.x, y: cursorPoint.y, pinching }) // 1-x: coherente con el espejado
          );
        }
      }
    }
    gestureCameraStatus.textContent = statusParts.join(" · ");
  } else {
    gestureCameraStatus.textContent = "Buscando tu mano…";
  }
  if (!sawScrollHand) scrollPrevY = null;
  gestureCtx.restore();
}

gestureToggle.addEventListener("click", () => {
  if (gesturesActive) stopGestures();
  else startGestures();
});

/* ---------- Herramientas ---------- */

async function loadTools() {
  const list = document.getElementById("tool-list");
  try {
    const tools = await api("/api/v1/tools");
    list.innerHTML = "";
    tools.forEach((tool) => {
      const card = document.createElement("div");
      card.className = "card";
      card.innerHTML = `
        <div class="card-info">
          <span class="card-title">${esc(tool.name)}</span>
          <span class="card-subtitle">${esc(tool.description)}</span>
        </div>
      `;
      list.appendChild(card);
    });
  } catch (err) {
    list.innerHTML = `<div class="empty-state">Error cargando herramientas: ${esc(err.message)}</div>`;
  }
}
document.getElementById("refresh-tools").addEventListener("click", loadTools);

/* ---------- Configuración ---------- */

function renderSettings() {
  const body = document.getElementById("settings-body");
  body.innerHTML = `
    <div class="card">
      <div class="card-info">
        <span class="card-title">Servidor</span>
        <span class="card-subtitle">${esc(API_URL)}</span>
      </div>
      <button type="button" class="secondary" id="settings-reset-url">Cambiar</button>
    </div>
    <div class="card">
      <div class="card-info">
        <span class="card-title">Nombre del saludo</span>
        <span class="card-subtitle">${USER_NAME ? esc(USER_NAME) : "Sin configurar — se saluda sin nombre"}</span>
      </div>
      <span class="badge">ATLAS_USER_NAME en backend/.env</span>
    </div>
    <div class="card">
      <div class="card-info">
        <span class="card-title">Cerrar sesión</span>
        <span class="card-subtitle">Borra el token guardado en este navegador</span>
      </div>
      <button type="button" class="secondary" id="settings-logout">Salir</button>
    </div>
  `;
  document.getElementById("settings-reset-url").addEventListener("click", () => {
    localStorage.removeItem("atlas_dashboard_api_url");
    logout();
  });
  document.getElementById("settings-logout").addEventListener("click", logout);
}

/* ---------- Actividad (AuditLog) ---------- */

/* Nombre legible por tool. El AuditLog guarda el identificador técnico
   (`get_current_time`); mostrarlo crudo en el panel de inicio se lee como
   ruido. Las que no estén acá caen al identificador, que es lo honesto:
   preferible el nombre real a una descripción inventada. */
const TOOL_LABELS = {
  get_current_time: "Consultaste la hora",
  get_system_info: "Consultaste el estado del equipo",
  list_processes: "Listaste los procesos",
  open_application: "Abriste una aplicación",
  close_application: "Cerraste una aplicación",
  open_file: "Abriste un archivo",
  control_media: "Controlaste la reproducción",
  list_files: "Listaste archivos",
  search_files: "Buscaste archivos",
  create_memory: "ATLAS guardó algo en memoria",
  search_memory: "ATLAS consultó su memoria",
  list_devices: "Listaste los dispositivos",
  set_device_state: "Cambiaste un dispositivo",
  control_room: "Controlaste una habitación",
  run_routine: "Ejecutaste una rutina",
  analyze_screenshot: "ATLAS miró la pantalla",
  search_wikipedia: "Buscaste en Wikipedia",
  get_weather: "Consultaste el clima",
  search_youtube: "Buscaste en YouTube",
  search_spotify: "Buscaste en Spotify",
  create_reminder: "Creaste un recordatorio",
  list_reminders: "Consultaste tus recordatorios",
};

function describeTool(name) {
  return TOOL_LABELS[name] || name;
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
    entries.forEach((entry) => {
      const card = document.createElement("div");
      card.className = "card";
      card.innerHTML = `
        <div class="card-info">
          <span class="card-title">${esc(entry.tool_name)}</span>
          <span class="card-subtitle">${esc(entry.result_summary || "")}</span>
        </div>
        <span class="badge ${entry.success ? "" : "fail"}">${entry.success ? esc(entry.risk_level) : "falló"} · ${esc(new Date(entry.created_at).toLocaleTimeString())}</span>
      `;
      list.appendChild(card);
    });

    homeList.innerHTML = "";
    entries.slice(0, 6).forEach((entry) => {
      const row = document.createElement("div");
      row.className = `timeline-row ${entry.success ? "" : "failed"}`;
      const time = new Date(entry.created_at).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
      row.innerHTML = `
        <span class="timeline-time">${esc(time)}</span>
        <span class="timeline-mark"></span>
        <span class="timeline-text">
          <strong>${esc(describeTool(entry.tool_name))}</strong>
          ${entry.result_summary ? `<em>${esc(entry.result_summary)}</em>` : ""}
        </span>
      `;
      homeList.appendChild(row);
    });
  } catch (err) {
    list.innerHTML = `<div class="empty-state">Error cargando actividad: ${esc(err.message)}</div>`;
    homeList.innerHTML = "";
  }
}
document.getElementById("refresh-activity").addEventListener("click", loadActivity);

/* ---------- Métricas del sistema (anillos + sparklines reales) ---------- */

// Historial de muestras reales para dibujar las sparklines. No hay datos
// sintéticos: la línea arranca vacía y se va llenando con cada sondeo.
const NET_HISTORY = [];
const TEMP_HISTORY = [];
const HISTORY_MAX = 40;

function setRing(id, valueId, percent) {
  const pct = Math.max(0, Math.min(100, Math.round(percent)));
  document.getElementById(id).style.setProperty("--pct", pct);
  document.getElementById(valueId).textContent = `${pct}%`;
}

function drawSparkline(canvasId, history) {
  const canvas = document.getElementById(canvasId);
  const ctx = canvas.getContext("2d");
  const w = canvas.width;
  const h = canvas.height;
  ctx.clearRect(0, 0, w, h);
  if (history.length < 2) return;

  const max = Math.max(...history, 0.001); // evita dividir por cero con la red en reposo
  const min = Math.min(...history, 0);
  const range = max - min || 1;
  const stepX = w / (history.length - 1);

  ctx.beginPath();
  history.forEach((value, i) => {
    const x = i * stepX;
    const y = h - 3 - ((value - min) / range) * (h - 6);
    if (i === 0) ctx.moveTo(x, y);
    else ctx.lineTo(x, y);
  });
  ctx.strokeStyle = "#22d3ee";
  ctx.lineWidth = 1.5;
  ctx.stroke();

  // Relleno debajo de la línea, para que se lea de un vistazo.
  ctx.lineTo(w, h);
  ctx.lineTo(0, h);
  ctx.closePath();
  ctx.fillStyle = "rgba(34, 211, 238, 0.10)";
  ctx.fill();
}

function formatUptime(seconds) {
  const days = Math.floor(seconds / 86400);
  const hours = Math.floor((seconds % 86400) / 3600);
  const minutes = Math.floor((seconds % 3600) / 60);
  if (days) return `${days}d ${hours}h`;
  if (hours) return `${hours}h ${minutes}m`;
  return `${minutes}m`;
}

function pushHistory(history, value) {
  history.push(value);
  if (history.length > HISTORY_MAX) history.shift();
}

async function pollSystemStatus() {
  try {
    const status = await api("/api/v1/system/status");
    setRing("ring-cpu", "ring-cpu-value", status.cpu_percent);
    setRing("ring-ram", "ring-ram-value", status.ram_percent);
    setRing("ring-disk", "ring-disk-value", status.disk_percent);

    const netTotal = (status.net_recv_mbps || 0) + (status.net_sent_mbps || 0);
    document.getElementById("metric-net").textContent = `${netTotal.toFixed(1)} Mbps`;
    pushHistory(NET_HISTORY, netTotal);
    drawSparkline("spark-net", NET_HISTORY);

    // cpu_temp_c es null en equipos que no exponen el sensor (común en
    // desktops con Windows) — ahí la tarjeta simplemente no se muestra.
    const tempWrap = document.getElementById("metric-temp-wrap");
    if (status.cpu_temp_c != null) {
      tempWrap.classList.remove("hidden");
      document.getElementById("metric-temp").textContent = `${status.cpu_temp_c} °C`;
      pushHistory(TEMP_HISTORY, status.cpu_temp_c);
      drawSparkline("spark-temp", TEMP_HISTORY);
    } else {
      tempWrap.classList.add("hidden");
    }

    if (status.uptime_seconds != null) {
      document.getElementById("metric-uptime").textContent = formatUptime(status.uptime_seconds);
    }
  } catch {
    /* el próximo sondeo lo reintenta; no vale la pena mostrar error acá */
  }
  if (TOKEN) setTimeout(pollSystemStatus, 4000);
}

/* ---------- Visualizadores de audio (orbe, hero, barra inferior) ---------- */
/* Nada de animación falsa: todo lo que se mueve sale de muestras reales del
   micrófono o del audio de respuesta de ATLAS (AnalyserNode). En reposo se
   dibuja una línea plana, que es la verdad: no hay audio. */

const orbButton = document.getElementById("orb-button");
const orbCanvas = document.getElementById("orb-canvas");
const orbCtx = orbCanvas.getContext("2d");
const orbStatus = document.getElementById("orb-status");
const listenLabel = document.getElementById("listen-label");
const listenMic = document.getElementById("listen-mic");

const heroWaveLeft = document.getElementById("hero-wave-left");
const heroWaveRight = document.getElementById("hero-wave-right");
const listenWave = document.getElementById("listen-wave");

let orbAudioCtx = null;
let orbAnalyser = null;
let orbDataArray = null;
let orbRafId = null;
let orbStream = null;
let mediaRecorder = null;
let audioChunks = [];
let orbRecording = false;

/* Línea plana de reposo: es la verdad (no hay audio sonando), pero se
   dibuja con un degradado que se desvanece en los bordes para que se lea
   como parte del diseño y no como un canvas roto. */
function drawFlatLine(canvas) {
  const ctx = canvas.getContext("2d");
  const w = canvas.width;
  const h = canvas.height;
  ctx.clearRect(0, 0, w, h);

  const gradient = ctx.createLinearGradient(0, 0, w, 0);
  gradient.addColorStop(0, "rgba(34, 211, 238, 0)");
  gradient.addColorStop(0.5, "rgba(34, 211, 238, 0.45)");
  gradient.addColorStop(1, "rgba(34, 211, 238, 0)");

  ctx.beginPath();
  ctx.moveTo(0, h / 2);
  ctx.lineTo(w, h / 2);
  ctx.strokeStyle = gradient;
  ctx.lineWidth = 1.5;
  ctx.stroke();
}

function drawIdleVisuals() {
  orbCtx.clearRect(0, 0, orbCanvas.width, orbCanvas.height);
  drawOrbRings();
  drawFlatLine(heroWaveLeft);
  drawFlatLine(heroWaveRight);
  drawFlatLine(listenWave);
}

/* Anillos concéntricos estáticos del orbe: decoración de marco, no una
   representación de datos (por eso no pretenden "moverse con la voz"). */
function drawOrbRings() {
  const w = orbCanvas.width;
  const cx = w / 2;
  const cy = orbCanvas.height / 2;

  // Halo suave detrás de todo, para que el orbe se despegue del fondo.
  const glow = orbCtx.createRadialGradient(cx, cy, 10, cx, cy, 128);
  glow.addColorStop(0, "rgba(34, 211, 238, 0.16)");
  glow.addColorStop(0.55, "rgba(34, 211, 238, 0.05)");
  glow.addColorStop(1, "rgba(34, 211, 238, 0)");
  orbCtx.fillStyle = glow;
  orbCtx.fillRect(0, 0, w, orbCanvas.height);

  [126, 108, 90, 70].forEach((radius, i) => {
    orbCtx.beginPath();
    orbCtx.arc(cx, cy, radius, 0, Math.PI * 2);
    orbCtx.strokeStyle = `rgba(34, 211, 238, ${0.13 + i * 0.06})`;
    orbCtx.lineWidth = 1;
    orbCtx.stroke();
  });
}

/* Onda circular del orbe, con muestras reales del AnalyserNode. */
function drawOrbWaveform(dataArray) {
  const w = orbCanvas.width;
  const h = orbCanvas.height;
  const cx = w / 2;
  const cy = h / 2;
  const baseRadius = 86;

  orbCtx.clearRect(0, 0, w, h);
  drawOrbRings();

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
  orbCtx.strokeStyle = "#22d3ee";
  orbCtx.lineWidth = 2;
  orbCtx.stroke();
  orbCtx.fillStyle = "rgba(34, 211, 238, 0.10)";
  orbCtx.fill();
}

/* Onda lineal (hero laterales y barra inferior), mismas muestras reales.
   `mirrored` invierte el eje X para que el lado izquierdo del hero fluya
   hacia el orbe, como en el diseño. */
function drawLinearWave(canvas, dataArray, { mirrored = false } = {}) {
  const ctx = canvas.getContext("2d");
  const w = canvas.width;
  const h = canvas.height;
  const mid = h / 2;

  ctx.clearRect(0, 0, w, h);
  ctx.beginPath();
  const step = w / (dataArray.length - 1);
  for (let i = 0; i < dataArray.length; i++) {
    const amplitude = (dataArray[i] - 128) / 128;
    const index = mirrored ? dataArray.length - 1 - i : i;
    const x = index * step;
    const y = mid - amplitude * (h / 2 - 4);
    if (i === 0) ctx.moveTo(x, y);
    else ctx.lineTo(x, y);
  }
  ctx.strokeStyle = "#22d3ee";
  ctx.lineWidth = 1.5;
  ctx.stroke();
}

function drawAllWaves(dataArray) {
  drawOrbWaveform(dataArray);
  drawLinearWave(heroWaveLeft, dataArray, { mirrored: true });
  drawLinearWave(heroWaveRight, dataArray);
  drawLinearWave(listenWave, dataArray);
}

function drawOrbFrame() {
  if (!orbAnalyser) return;
  orbRafId = requestAnimationFrame(drawOrbFrame);
  orbAnalyser.getByteTimeDomainData(orbDataArray);
  drawAllWaves(orbDataArray);
}

function setListeningUI(active, label) {
  orbButton.classList.toggle("listening", active);
  listenMic.classList.toggle("recording", active);
  listenLabel.textContent = label;
  orbStatus.textContent = label;
}

/* Corte automático por silencio, para el flujo de wake word: tras detectar
   la palabra nadie va a tocar "detener", así que la grabación tiene que
   cerrarse sola. Equivale a record_command_until_silence() del escritorio. */
const COMMAND_MAX_MS = 9000;      // tope duro, aunque siga habiendo ruido
const COMMAND_SILENCE_MS = 1600;  // cuánto silencio corta la grabación
const COMMAND_SPEECH_LEVEL = 0.045; // amplitud mínima para contar como voz

async function startOrbRecording({ autoStopAfterSilence = false } = {}) {
  try {
    orbStream = await navigator.mediaDevices.getUserMedia({ audio: true });
  } catch (err) {
    setListeningUI(false, `No pude acceder al micrófono: ${err.message}`);
    if (autoStopAfterSilence) wakeEngine.resume();
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
  setListeningUI(true, "ATLAS está escuchando…");
  drawOrbFrame();

  if (autoStopAfterSilence) scheduleSilenceStop();
}

/* Vigila el nivel real del micrófono y corta cuando deja de haber voz.
   Reutiliza el AnalyserNode que ya alimenta al orbe. */
function scheduleSilenceStop() {
  const startedAt = Date.now();
  let lastSpeechAt = Date.now();
  let heardSpeech = false;

  const watch = () => {
    if (!orbRecording) return;

    orbAnalyser.getByteTimeDomainData(orbDataArray);
    let peak = 0;
    for (let i = 0; i < orbDataArray.length; i++) {
      peak = Math.max(peak, Math.abs((orbDataArray[i] - 128) / 128));
    }
    if (peak >= COMMAND_SPEECH_LEVEL) {
      heardSpeech = true;
      lastSpeechAt = Date.now();
    }

    const elapsed = Date.now() - startedAt;
    const quietFor = Date.now() - lastSpeechAt;
    // Solo corta por silencio si antes escuchó algo: si no, esperaría el
    // tope duro cuando la palabra se detectó por un falso positivo.
    if (elapsed >= COMMAND_MAX_MS || (heardSpeech && quietFor >= COMMAND_SILENCE_MS)) {
      stopOrbRecording();
      return;
    }
    setTimeout(watch, 150);
  };
  setTimeout(watch, 400); // margen para que el usuario empiece a hablar
}

function stopOrbRecording() {
  orbRecording = false;
  setListeningUI(false, "Procesando…");

  if (orbRafId) cancelAnimationFrame(orbRafId);
  orbRafId = null;
  drawIdleVisuals();

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

function toggleRecording() {
  if (orbRecording) stopOrbRecording();
  else startOrbRecording();
}

orbButton.addEventListener("click", toggleRecording);
listenMic.addEventListener("click", toggleRecording);
document.getElementById("hero-mic").addEventListener("click", toggleRecording);

/* ---------- Escucha continua (wake word) ---------- */
/* Mismo motor que la PWA (shared/wake-word.js) y misma estrategia que el
   cliente de escritorio: buffer deslizante + filtro de energía local +
   Whisper. Apagado por defecto: mantiene el micrófono abierto de forma
   continua, así que tiene que ser una decisión explícita del usuario. */

const listenWake = document.getElementById("listen-wake");

const wakeEngine = new WakeWordEngine({
  workletUrl: "/shared/wake-processor.js",
  wakeWord: WAKE_WORD,
  transcribe: async (wavBlob) => {
    const form = new FormData();
    form.append("audio", wavBlob, "wake.wav");
    const result = await api("/api/v1/voice/transcribe", { method: "POST", body: form });
    return result.text || "";
  },
  onActivated: onWakeWordDetected,
  onStatus: (state, detail) => {
    if (state === "error") {
      appendBubble("atlas", `(${detail})`);
      renderWakeButton(false);
    }
  },
});

function renderWakeButton(active) {
  listenWake.classList.toggle("active", active);
  listenWake.title = active
    ? `Escucha continua activa — decí "${WAKE_WORD}"`
    : "Escucha continua: activar para hablarle sin tocar nada";
  if (active) {
    listenLabel.textContent = `Escuchando… decí "${WAKE_WORD}"`;
  } else if (!orbRecording) {
    listenLabel.textContent = "ATLAS en espera";
  }
}

listenWake.addEventListener("click", async () => {
  if (wakeEngine.isActive) {
    wakeEngine.stop();
    renderWakeButton(false);
    return;
  }
  // La palabra puede haber llegado del backend después de construir el
  // motor: se refresca antes de arrancar.
  wakeEngine._wakeWord = WAKE_WORD;
  await wakeEngine.start();
  renderWakeButton(wakeEngine.isActive);
});

/* Al detectar la palabra: pausar la escucha (si no, ATLAS se oye a sí mismo
   por los parlantes y se vuelve a disparar), grabar el comando y reanudar.
   Mismo criterio que el cliente de escritorio. */
async function onWakeWordDetected() {
  wakeEngine.pause();
  goToView("chat");
  appendBubble("atlas", "(Te escuché — decime qué necesitás.)");
  await startOrbRecording({ autoStopAfterSilence: true });
}

/* Reanuda la escucha continua si el usuario la tenía encendida. Se llama al
   final de cada camino posible (respondió con voz, respondió sin voz, no se
   entendió, hubo error): si alguno se lo saltea, la escucha queda muerta
   sin que se note. */
function resumeWakeIfActive() {
  if (wakeEngine.isActive) {
    wakeEngine.resume();
    renderWakeButton(true);
  }
}

async function transcribeAndSend(blob) {
  const form = new FormData();
  form.append("audio", blob, "audio.webm");
  let spoke = false;
  try {
    const result = await api("/api/v1/voice/transcribe", { method: "POST", body: form });
    setListeningUI(false, "ATLAS en espera");
    if (result.text && result.text.trim()) {
      spoke = true;
      // sendChat dispara speak(), y speak() reanuda la escucha al terminar.
      await sendChat(result.text, { switchView: true });
    } else {
      appendBubble("atlas", "(No entendí el comando, sigo atento.)");
    }
  } catch (err) {
    setListeningUI(false, "ATLAS en espera");
    appendBubble("atlas", `(error transcribiendo: ${err.message})`);
  }
  if (!spoke) resumeWakeIfActive();
}

/* ---------- Shazam: reconocer la canción que está sonando ---------- */
/* No es una tool de la IA a propósito: es una subida directa, mismo criterio
   que /voice/transcribe y /vision/analyze — el usuario ya decidió
   explícitamente grabar, no hace falta que Claude lo decida por él. Por eso
   pedírselo por chat no funciona: el modelo no tiene acceso al micrófono. */

const listenShazam = document.getElementById("listen-shazam");
const SHAZAM_RECORD_MS = 6000; // AudD recomienda 3-10s de audio

listenShazam.addEventListener("click", async () => {
  if (listenShazam.disabled || orbRecording) return;
  let stream;
  try {
    stream = await navigator.mediaDevices.getUserMedia({ audio: true });
  } catch (err) {
    appendBubble("atlas", `(no pude acceder al micrófono: ${err.message})`);
    return;
  }

  const chunks = [];
  const recorder = new MediaRecorder(stream);
  recorder.ondataavailable = (e) => chunks.push(e.data);
  recorder.onstop = async () => {
    stream.getTracks().forEach((t) => t.stop());
    listenShazam.classList.remove("recording");
    listenShazam.disabled = false;
    setListeningUI(false, "ATLAS en espera");
    await identifySong(new Blob(chunks, { type: recorder.mimeType || "audio/webm" }));
  };

  recorder.start();
  listenShazam.classList.add("recording");
  listenShazam.disabled = true;
  goToView("chat");
  appendBubble("user", "(Shazam: escuchando la canción…)");
  setListeningUI(true, "Identificando la canción…");
  setTimeout(() => recorder.stop(), SHAZAM_RECORD_MS);
});

async function identifySong(blob) {
  const form = new FormData();
  form.append("audio", blob, "audio.webm");
  try {
    const result = await api("/api/v1/music/identify", { method: "POST", body: form });
    if (!result.found) {
      appendBubble("atlas", "No reconocí ninguna canción — probá de nuevo con más volumen.");
      return;
    }
    let reply = `${result.title} — ${result.artist}`;
    if (result.album) reply += ` (${result.album})`;
    if (result.song_link) reply += `\n${result.song_link}`;
    appendBubble("atlas", reply);
  } catch (err) {
    appendBubble("atlas", `(error reconociendo la canción: ${err.message})`);
  }
}

/* ---------- Voz de ATLAS: reproducción con los mismos visualizadores ---------- */

/* ---------- Reproducción de la voz de ATLAS ----------
 *
 * Dos problemas de autoplay que hay que resolver juntos:
 *
 *  1. Un `AudioContext` nuevo arranca **suspendido** si no hubo un gesto
 *     reciente. Como el audio pasa por el contexto para llegar a los
 *     parlantes, queda mudo — y `play()` ni siquiera falla.
 *  2. En móvil el permiso **caduca**: el toque en "Enviar" ya no vale
 *     cuando el audio llega, varios segundos después.
 *
 * Por eso no se crea un `new Audio()` por respuesta: se reutiliza SIEMPRE
 * el mismo elemento y el mismo grafo de audio, desbloqueados en el primer
 * gesto del usuario. `createMediaElementSource` además solo puede llamarse
 * una vez por elemento, así que reutilizar es obligatorio, no una mejora.
 */

const speechAudio = new Audio();
speechAudio.preload = "auto";
// Dentro del DOM y no suelto: algunos navegadores móviles solo reproducen
// de forma confiable elementos que están en el documento.
speechAudio.hidden = true;
document.body.appendChild(speechAudio);
let speechCtx = null;
let speechAnalyser = null;
let speechData = null;
let audioUnlocked = false;

function unlockAudio() {
  if (audioUnlocked) return;
  try {
    if (!speechCtx) {
      speechCtx = new (window.AudioContext || window.webkitAudioContext)();
      const source = speechCtx.createMediaElementSource(speechAudio);
      speechAnalyser = speechCtx.createAnalyser();
      speechAnalyser.fftSize = 128;
      speechData = new Uint8Array(speechAnalyser.frequencyBinCount);
      source.connect(speechAnalyser);
      speechAnalyser.connect(speechCtx.destination); // esto sí debe sonar
    }
    speechCtx.resume().catch(() => {});
    // WAV mínimo y silencioso: alcanza para que el navegador marque el
    // elemento como autorizado por el usuario.
    speechAudio.src =
      "data:audio/wav;base64,UklGRiQAAABXQVZFZm10IBAAAAABAAEARKwAAIhYAQACABAAZGF0YQAAAAA=";
    speechAudio.play().then(() => {
      speechAudio.pause();
      speechAudio.currentTime = 0;
      audioUnlocked = true;
    }).catch(() => {
      /* se reintenta en el próximo gesto */
    });
  } catch {
    /* se reintenta en el próximo gesto */
  }
}
document.addEventListener("pointerdown", unlockAudio);
document.addEventListener("keydown", unlockAudio);

async function speak(text) {
  let response;
  try {
    response = await api("/api/v1/voice/speak", { method: "POST", body: JSON.stringify({ text }) });
  } catch {
    // La respuesta de texto ya se mostró; el audio es un extra. Pero la
    // escucha continua tiene que volver igual, o queda muerta en silencio.
    resumeWakeIfActive();
    return;
  }
  const blob = await response.blob();
  await playSpeech(URL.createObjectURL(blob));
}

async function playSpeech(url) {
  if (orbRecording) {
    resumeWakeIfActive(); // no pisar una grabación en curso
    return;
  }

  if (speechCtx && speechCtx.state === "suspended") {
    try { await speechCtx.resume(); } catch { /* se maneja abajo */ }
  }
  const visualize = speechCtx && speechCtx.state === "running";

  setListeningUI(true, "ATLAS está hablando…");

  let rafId;
  const finish = () => {
    if (rafId) cancelAnimationFrame(rafId);
    setListeningUI(false, "ATLAS en espera");
    drawIdleVisuals();
    // Recién ahora se reanuda la escucha: mientras ATLAS hablaba, su propia
    // voz por los parlantes habría vuelto a disparar la palabra.
    resumeWakeIfActive();
  };

  const draw = () => {
    if (speechAudio.paused || speechAudio.ended) return;
    rafId = requestAnimationFrame(draw);
    speechAnalyser.getByteTimeDomainData(speechData);
    drawAllWaves(speechData);
  };

  speechAudio.onended = finish;
  speechAudio.onerror = finish;
  speechAudio.src = url;

  try {
    await speechAudio.play();
    // Sin contexto reanudable no hay visualizador, pero sí voz: es preferible
    // oír a ATLAS sin la animación que tener la animación en silencio.
    if (visualize) draw();
  } catch (err) {
    appendBubble("atlas", `(No pude reproducir el audio: ${err.message}. Hacé clic en la página y volvé a pedirlo.)`);
    finish();
  }
}


/* ---------- Arranque ---------- */
/* Última línea del archivo a propósito: con una sesión guardada esto entra
   directo a la app, y enterApp() toca constantes declaradas a lo largo de
   todo el módulo. Llamarlo antes las encuentra sin inicializar. El login
   manual no tiene el problema porque corre desde un evento, ya evaluado
   el módulo entero — por eso el bug solo aparecía al recargar ya logueado. */
if (TOKEN) enterApp();
