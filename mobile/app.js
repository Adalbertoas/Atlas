"use strict";

/* ---------- Config / estado ---------- */

const DEFAULT_API_URL = `${location.protocol}//${location.hostname}:8000`;
let API_URL = localStorage.getItem("atlas_api_url") || DEFAULT_API_URL;
let TOKEN = localStorage.getItem("atlas_token") || null;
let CONVERSATION_ID = null;

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

loginForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  loginError.textContent = "";

  const password = document.getElementById("login-password").value;
  const customUrl = loginApiUrlInput.value.trim();
  API_URL = customUrl || DEFAULT_API_URL;

  try {
    const response = await fetch(`${API_URL}/api/v1/auth/login`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ password }),
    });
    if (!response.ok) throw new Error("Contraseña incorrecta.");
    const body = await response.json();
    TOKEN = body.access_token;
    localStorage.setItem("atlas_token", TOKEN);
    localStorage.setItem("atlas_api_url", API_URL);
    enterApp();
  } catch (err) {
    loginError.textContent = err.message || "No se pudo conectar al servidor.";
  }
});

function logout() {
  TOKEN = null;
  localStorage.removeItem("atlas_token");
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
}

async function checkConnection() {
  const statusEl = document.getElementById("connection-status");
  try {
    const response = await fetch(`${API_URL}/api/v1/system/health`);
    statusEl.textContent = response.ok ? `conectado (${API_URL})` : "sin conexión";
  } catch {
    statusEl.textContent = "sin conexión";
  }
}

/* Si el backend tiene el login desactivado (AUTH_ENABLED=false), acepta
   cualquier contraseña: se entra solo sin mostrar el formulario. Si no, el
   login falla y queda la pantalla de contraseña como siempre. */
async function tryAutoLogin() {
  try {
    const response = await fetch(`${API_URL}/api/v1/auth/login`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ password: "" }),
    });
    if (!response.ok) return;
    TOKEN = (await response.json()).access_token;
    localStorage.setItem("atlas_token", TOKEN);
    enterApp();
  } catch {
    /* backend inalcanzable — queda la pantalla de login */
  }
}

/* Si ya había un token guardado, entrar directo sin pedir contraseña de nuevo. */
if (TOKEN) enterApp();
else tryAutoLogin();

/* ---------- Navegación por tabs ---------- */

document.querySelectorAll(".tab-button").forEach((btn) => {
  btn.addEventListener("click", () => {
    document.querySelectorAll(".tab-button").forEach((b) => b.classList.remove("active"));
    document.querySelectorAll(".view").forEach((v) => v.classList.remove("active"));
    btn.classList.add("active");
    document.getElementById(`view-${btn.dataset.view}`).classList.add("active");
    // La cámara de gestos nunca debe quedar prendida sin que se la vea:
    // apagarla al salir de esa pestaña (sección 16: sin captura continua oculta).
    if (btn.dataset.view !== "gestures" && typeof stopGestures === "function") stopGestures();
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

/* ---------- Voz ---------- */

const voiceButton = document.getElementById("voice-button");
let mediaRecorder = null;
let audioChunks = [];

voiceButton.addEventListener("click", async () => {
  if (mediaRecorder && mediaRecorder.state === "recording") {
    mediaRecorder.stop();
    return;
  }
  try {
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    audioChunks = [];
    mediaRecorder = new MediaRecorder(stream);
    mediaRecorder.ondataavailable = (e) => audioChunks.push(e.data);
    mediaRecorder.onstop = async () => {
      stream.getTracks().forEach((track) => track.stop());
      voiceButton.classList.remove("recording");
      const blob = new Blob(audioChunks, { type: mediaRecorder.mimeType || "audio/webm" });
      await transcribeAndSend(blob);
    };
    mediaRecorder.start();
    voiceButton.classList.add("recording");
  } catch (err) {
    appendBubble("atlas", `(no pude acceder al micrófono: ${err.message})`);
  }
});

async function transcribeAndSend(blob) {
  const form = new FormData();
  form.append("audio", blob, "audio.webm");
  try {
    const result = await api("/api/v1/voice/transcribe", { method: "POST", body: form });
    if (result.text && result.text.trim()) {
      await sendChat(result.text);
    }
  } catch (err) {
    appendBubble("atlas", `(error transcribiendo: ${err.message})`);
  }
}

/* ---------- Foto (Fase 8: Visión) ---------- */

const photoButton = document.getElementById("photo-button");
const photoInput = document.getElementById("photo-input");

photoButton.addEventListener("click", () => photoInput.click());

photoInput.addEventListener("change", async () => {
  const file = photoInput.files[0];
  photoInput.value = ""; // permite volver a elegir la misma foto después
  if (!file) return;

  appendBubble("user", "📷 (foto)");
  const form = new FormData();
  form.append("image", file, file.name || "foto.jpg");
  try {
    const result = await api("/api/v1/vision/analyze", { method: "POST", body: form });
    appendBubble("atlas", result.description);
    speak(result.description);
  } catch (err) {
    appendBubble("atlas", `(error analizando la foto: ${err.message})`);
  }
});

async function speak(text) {
  try {
    const response = await api("/api/v1/voice/speak", { method: "POST", body: JSON.stringify({ text }) });
    const blob = await response.blob();
    const audio = new Audio(URL.createObjectURL(blob));
    audio.play().catch(() => {}); // el navegador puede bloquear autoplay sin interacción previa
  } catch {
    /* la respuesta de texto ya se mostró; el audio es un extra */
  }
}

/* ---------- Dispositivos ---------- */

const SAFE_ACTIONS = { LIGHT: "turn", SWITCH: "turn", PLUG: "turn", FAN: "turn", TV: "turn" };

async function loadDevices() {
  const list = document.getElementById("device-list");
  try {
    const devices = await api("/api/v1/devices");
    if (!devices.length) {
      list.innerHTML = '<div class="empty-state">No hay dispositivos. Configurá SMART_HOME_PROVIDER en el backend.</div>';
      return;
    }
    list.innerHTML = "";
    devices.forEach((device) => {
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
      list.appendChild(card);
    });
  } catch (err) {
    list.innerHTML = `<div class="empty-state">Error cargando dispositivos: ${err.message}</div>`;
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

/* ---------- Gestos: control del mouse de la PC con la cámara del celular ---------- */
/* La detección de la mano corre acá, en el navegador (MediaPipe Tasks Vision,
   único recurso cargado desde un CDN en todo el proyecto — evita instalar
   MediaPipe en Python, que no tenía wheel confiable para este entorno). Solo
   se manda por WebSocket la posición del índice y si hay pellizco — nunca
   video ni imágenes. */

const MEDIAPIPE_CDN = "https://cdn.jsdelivr.net/npm/@mediapipe/tasks-vision@0.10.14";
const HAND_MODEL_URL =
  "https://storage.googleapis.com/mediapipe-models/hand_landmarker/hand_landmarker/float16/1/hand_landmarker.task";
// Pinned WebGPU hand-tracking pipeline. It is preferred when the phone can
// run WebGPU and falls back to the existing compatibility engine otherwise.
const WEBGPU_VISION_COMMIT = "672367e2e7210cbb8bf3d2e0bf85c5f263e11dd1";
const WEBGPU_TRACKER_URL =
  `https://cdn.jsdelivr.net/gh/Sonified/webgpu-vision@${WEBGPU_VISION_COMMIT}/src/pipeline.js`;
// Umbral del pellizco como fracción del tamaño de la mano (muñeca→nudillo medio),
// no como distancia fija — así funciona igual sin importar qué tan cerca de la
// cámara esté la mano (una distancia normalizada fija era muy estricta cuando
// la mano estaba lejos, porque todo se achica junto con ella).
const PINCH_RATIO = 0.55;
const GESTURE_CALIBRATION_KEY = "atlas_gesture_calibration_v1";
const CALIBRATION_CAPTURE_MS = 2200;
const CURLED_RATIO = 0.9; // qué tan más cerca de la muñeca debe estar la punta que el nudillo (dedo doblado = puño)

let scrollPrevY = null; // posición anterior del gesto de scroll, para calcular el delta entre frames

const gesturesVideo = document.getElementById("gestures-video");
const gesturesCanvas = document.getElementById("gestures-canvas");
const gesturesCtx = gesturesCanvas.getContext("2d");
const gesturesStatus = document.getElementById("gestures-status");
const gesturesToggle = document.getElementById("gestures-toggle");
const gesturesCalibrate = document.getElementById("gestures-calibrate");
const gesturesResetCalibration = document.getElementById("gestures-reset-calibration");
const gesturesCalibrationHelp = document.getElementById("gestures-calibration-help");

let gesturesActive = false;
let gesturesStream = null;
let gesturesSocket = null;
let handLandmarker = null;
let gestureEngine = null;
let gesturesRafId = null;
let gestureFrameBusy = false;
let latestGestureResult = { landmarks: [], handedness: [] };
let latestCursorPoint = null;
let calibrationStep = null;
let calibrationSamples = [];
let calibrationFirstCorner = null;
let calibrationTimer = null;

function readGestureCalibration() {
  try {
    const calibration = JSON.parse(localStorage.getItem(GESTURE_CALIBRATION_KEY) || "null");
    if (!calibration || !Number.isFinite(calibration.minX) || !Number.isFinite(calibration.maxX)
      || !Number.isFinite(calibration.minY) || !Number.isFinite(calibration.maxY)
      || calibration.maxX - calibration.minX < 0.08 || calibration.maxY - calibration.minY < 0.08) return null;
    return calibration;
  } catch {
    return null;
  }
}

function clampUnit(value) {
  return Math.min(1, Math.max(0, value));
}

function mapCursorPoint(rawX, rawY) {
  const calibration = readGestureCalibration();
  if (!calibration) return { x: rawX, y: rawY };
  return {
    x: clampUnit((rawX - calibration.minX) / (calibration.maxX - calibration.minX)),
    y: clampUnit((rawY - calibration.minY) / (calibration.maxY - calibration.minY)),
  };
}

function updateCalibrationControls() {
  gesturesCalibrate.disabled = !gesturesActive || (calibrationStep !== null && calibrationStep !== "second");
  gesturesResetCalibration.disabled = !readGestureCalibration();
  if (calibrationStep === "first") {
    gesturesCalibrate.textContent = "Esperando esquina 1…";
  } else if (calibrationStep === "capturing") {
    gesturesCalibrate.textContent = "Esperando esquina 2…";
  } else if (calibrationStep === "second") {
    gesturesCalibrate.textContent = "Capturar esquina 2";
  } else {
    gesturesCalibrate.textContent = readGestureCalibration() ? "🎯 Recalibrar alcance" : "🎯 Calibrar alcance";
  }
}

function cancelCalibration(message = null) {
  if (calibrationTimer) clearTimeout(calibrationTimer);
  calibrationTimer = null;
  calibrationStep = null;
  calibrationSamples = [];
  calibrationFirstCorner = null;
  if (message) gesturesCalibrationHelp.textContent = message;
  updateCalibrationControls();
}

function finishCalibrationCapture() {
  calibrationTimer = null;
  if (calibrationSamples.length < 6) {
    cancelCalibration("No vi tu mano el tiempo suficiente. Intentá otra vez con buena luz.");
    return;
  }
  const point = calibrationSamples.reduce(
    (total, sample) => ({ x: total.x + sample.x, y: total.y + sample.y }), { x: 0, y: 0 }
  );
  point.x /= calibrationSamples.length;
  point.y /= calibrationSamples.length;

  if (calibrationStep === "first") {
    calibrationFirstCorner = point;
    calibrationStep = "second";
    gesturesCalibrationHelp.textContent = "Esquina 1 guardada. Llevá tu mano abajo a la derecha y tocá “Capturar esquina 2”.";
    updateCalibrationControls();
    return;
  }

  const calibration = {
    minX: Math.min(calibrationFirstCorner.x, point.x), maxX: Math.max(calibrationFirstCorner.x, point.x),
    minY: Math.min(calibrationFirstCorner.y, point.y), maxY: Math.max(calibrationFirstCorner.y, point.y),
  };
  if (calibration.maxX - calibration.minX < 0.08 || calibration.maxY - calibration.minY < 0.08) {
    cancelCalibration("Las esquinas quedaron muy cerca. Repetí usando un rango más amplio.");
    return;
  }
  localStorage.setItem(GESTURE_CALIBRATION_KEY, JSON.stringify(calibration));
  cancelCalibration("Alcance calibrado. Tu rango de mano ahora cubre todo el escritorio virtual.");
}

function captureCalibrationCorner() {
  if (!gesturesActive) {
    gesturesCalibrationHelp.textContent = "Primero activá el control por gestos.";
    return;
  }
  if (calibrationStep === "second") {
    calibrationStep = "capturing";
    calibrationSamples = [];
    gesturesCalibrationHelp.textContent = "Mantené la mano abajo a la derecha durante 2 segundos…";
  } else {
    calibrationStep = "first";
    calibrationSamples = [];
    gesturesCalibrationHelp.textContent = "Mantené la mano arriba a la izquierda durante 2 segundos…";
  }
  calibrationTimer = setTimeout(finishCalibrationCapture, CALIBRATION_CAPTURE_MS);
  updateCalibrationControls();
}

async function loadGestureEngine() {
  if (gestureEngine) return gestureEngine;

  if (navigator.gpu && "VideoFrame" in window) {
    try {
      gesturesStatus.textContent = "Preparando motor WebGPU de alta precision...";
      const { HandTracker } = await import(WEBGPU_TRACKER_URL);
      const tracker = new HandTracker();
      await tracker.init((message) => {
        gesturesStatus.textContent = `WebGPU: ${message}`;
      }, { variant: "large-f16", palmEngine: "wgsl" });
      gestureEngine = {
        name: "WebGPU",
        async detect(video) {
          const result = await tracker.processFrame(video);
          return (result.hands || []).filter(Boolean);
        },
        dispose() {
          tracker.palmWorker?.terminate?.();
          tracker.landmarkWorkers?.forEach((worker) => worker.worker?.terminate?.());
        },
      };
      return gestureEngine;
    } catch (err) {
      console.warn("WebGPU gestures unavailable; switching to compatibility engine.", err);
    }
  }

  gesturesStatus.textContent = "Usando motor compatible de deteccion...";
  const landmarker = await loadHandLandmarker();
  gestureEngine = {
    name: "Compatible",
    detect(video) {
      const result = landmarker.detectForVideo(video, performance.now());
      return (result.landmarks || []).map((landmarks, index) => ({
        landmarks,
        handedness: result.handedness?.[index]?.[0]?.categoryName || null,
      }));
    },
    dispose() {},
  };
  return gestureEngine;
}

async function loadHandLandmarker() {
  if (handLandmarker) return handLandmarker;
  gesturesStatus.textContent = "Cargando modelo de detección de manos…";
  const { HandLandmarker, FilesetResolver } = await import(MEDIAPIPE_CDN);
  const vision = await FilesetResolver.forVisionTasks(`${MEDIAPIPE_CDN}/wasm`);
  handLandmarker = await HandLandmarker.createFromOptions(vision, {
    baseOptions: { modelAssetPath: HAND_MODEL_URL, delegate: "GPU" },
    numHands: 2, // mano derecha = cursor/clic, mano izquierda = puño para scroll
    runningMode: "VIDEO",
    // Un puño cerrado es más difícil de reconocer como "mano" que una mano
    // abierta apuntando (menos dedos visibles/articulados) — bajar estos
    // umbrales ayuda a que el detector no lo descarte.
    minHandDetectionConfidence: 0.3,
    minHandPresenceConfidence: 0.3,
    minTrackingConfidence: 0.3,
  });
  return handLandmarker;
}

async function startGestures() {
  try {
    gesturesStream = await navigator.mediaDevices.getUserMedia({
      video: { facingMode: "user", width: 480, height: 360 },
    });
  } catch (err) {
    gesturesStatus.textContent = `No pude acceder a la cámara: ${err.message}`;
    return;
  }

  gesturesVideo.srcObject = gesturesStream;
  await gesturesVideo.play();
  gesturesCanvas.width = gesturesVideo.videoWidth || 480;
  gesturesCanvas.height = gesturesVideo.videoHeight || 360;

  try {
    await loadGestureEngine();
  } catch (err) {
    gesturesStatus.textContent = `No pude cargar el modelo de manos: ${err.message}`;
    stopGestures();
    return;
  }

  const wsUrl = `${API_URL.replace(/^http/, "ws")}/api/v1/gestures/stream`;
  gesturesSocket = new WebSocket(wsUrl);
  gesturesSocket.addEventListener("open", () => {
    gesturesSocket.send(JSON.stringify({ token: TOKEN }));
  });
  gesturesSocket.addEventListener("close", () => {
    if (gesturesActive) stopGestures();
  });

  gesturesActive = true;
  gesturesToggle.textContent = "🖐️ Desactivar control por gestos";
  gesturesStatus.textContent = `${gestureEngine.name}: buscando tu mano…`;
  updateCalibrationControls();
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
  gestureEngine?.dispose?.();
  gestureEngine = null;
  gestureFrameBusy = false;
  latestGestureResult = { landmarks: [], handedness: [] };
  latestCursorPoint = null;
  cancelCalibration();
  gesturesCtx.clearRect(0, 0, gesturesCanvas.width, gesturesCanvas.height);
  gesturesStatus.textContent = "Cámara apagada";
  gesturesToggle.textContent = "🖐️ Activar control por gestos";
}

function detectLoop() {
  if (!gesturesActive) return;
  gesturesRafId = requestAnimationFrame(detectLoop);
  if (!gestureEngine || gesturesVideo.readyState < 2 || gestureFrameBusy) return;

  // The WebGPU path returns asynchronously. Retain the last complete frame
  // while the next inference runs so the cursor never stalls the UI thread.
  gestureFrameBusy = true;
  Promise.resolve(gestureEngine.detect(gesturesVideo))
    .then((hands) => {
      latestGestureResult = {
        landmarks: hands.map((hand) => hand.landmarks),
        handedness: hands.map((hand) => hand.handedness ? [{ categoryName: hand.handedness }] : []),
      };
    })
    .catch((err) => console.warn("Gesture frame failed", err))
    .finally(() => { gestureFrameBusy = false; });
  const result = latestGestureResult;
  gesturesCtx.save();
  gesturesCtx.clearRect(0, 0, gesturesCanvas.width, gesturesCanvas.height);
  // Espejado: cámara frontal "selfie" — así mover la mano hacia tu derecha
  // real mueve el cursor hacia la derecha, de forma intuitiva.
  gesturesCtx.translate(gesturesCanvas.width, 0);
  gesturesCtx.scale(-1, 1);

  // Dos manos: la mano izquierda (vista por la cámara) hace scroll con el
  // puño; la mano derecha mueve el cursor y hace clic con el pellizco. Así
  // nunca se confunden entre sí, cada mano tiene un solo trabajo.
  let sawScrollHand = false;

  if (result.landmarks && result.landmarks.length > 0) {
    const statusParts = [];
    for (let i = 0; i < result.landmarks.length; i++) {
      const hand = result.landmarks[i];
      gesturesCtx.fillStyle = "#4fc3f7";
      hand.forEach((point) => {
        gesturesCtx.beginPath();
        gesturesCtx.arc(point.x * gesturesCanvas.width, point.y * gesturesCanvas.height, 4, 0, Math.PI * 2);
        gesturesCtx.fill();
      });

      // La clasificación de MediaPipe es sobre el frame de cámara tal cual
      // (sin el espejado que solo aplicamos al dibujar en pantalla).
      const handedness = result.handedness && result.handedness[i] && result.handedness[i][0];
      const isScrollHand = handedness && handedness.categoryName === "Left";

      const wrist = hand[0];
      const indexTip = hand[8];
      const dist = (a, b) => Math.hypot(a.x - b.x, a.y - b.y);

      if (isScrollHand) {
        sawScrollHand = true;
        const middleTip = hand[12];
        const ringTip = hand[16];
        const pinkyTip = hand[20];
        const indexCurled = dist(indexTip, wrist) < dist(hand[6], wrist) * CURLED_RATIO;
        const middleCurled = dist(middleTip, wrist) < dist(hand[10], wrist) * CURLED_RATIO;
        const ringCurled = dist(ringTip, wrist) < dist(hand[14], wrist) * CURLED_RATIO;
        const pinkyCurled = dist(pinkyTip, wrist) < dist(hand[18], wrist) * CURLED_RATIO;
        const fist = indexCurled && middleCurled && ringCurled && pinkyCurled;

        if (fist) {
          // Centro de la palma (muñeca + nudillo medio) — más estable que una punta de dedo sola.
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
        const handSize = dist(wrist, hand[9]); // muñeca → nudillo medio, escala con la distancia a la cámara
        const pinching = dist(indexTip, thumbTip) < handSize * PINCH_RATIO;
        // El cursor sigue el nudillo del índice (base del dedo, landmark 5),
        // no la punta: la punta se mueve hacia el pulgar al pellizcar, lo que
        // desplazaba el cursor justo al querer hacer clic con la mano quieta.
        // El nudillo casi no se mueve durante el pellizco.
        const cursorPoint = hand[5];
        const rawCursor = { x: 1 - cursorPoint.x, y: cursorPoint.y };
        latestCursorPoint = rawCursor;
        if (calibrationStep === "first" || calibrationStep === "capturing") {
          calibrationSamples.push(rawCursor);
          if (calibrationSamples.length > 90) calibrationSamples.shift();
        }
        const mappedCursor = mapCursorPoint(rawCursor.x, rawCursor.y);
        statusParts.push(pinching ? "Pellizco (clic)" : "Cursor");
        if (!calibrationStep && gesturesSocket && gesturesSocket.readyState === WebSocket.OPEN) {
          gesturesSocket.send(
            JSON.stringify({ x: mappedCursor.x, y: mappedCursor.y, pinching })
          );
        }
      }
    }
    gesturesStatus.textContent = `${gestureEngine.name}: ${statusParts.join(" · ")}`;
  } else {
    gesturesStatus.textContent = `${gestureEngine.name}: buscando tu mano…`;
  }
  if (!sawScrollHand) scrollPrevY = null;
  gesturesCtx.restore();
}

gesturesToggle.addEventListener("click", () => {
  if (gesturesActive) stopGestures();
  else startGestures();
});

gesturesCalibrate.addEventListener("click", captureCalibrationCorner);
gesturesResetCalibration.addEventListener("click", () => {
  localStorage.removeItem(GESTURE_CALIBRATION_KEY);
  gesturesCalibrationHelp.textContent = "Calibración eliminada. Atlas volvió al rango completo de la cámara.";
  updateCalibrationControls();
});
updateCalibrationControls();

/* ---------- Service worker (PWA instalable) ---------- */

if ("serviceWorker" in navigator) {
  window.addEventListener("load", () => {
    navigator.serviceWorker.register("./sw.js").catch(() => {});
  });
}
