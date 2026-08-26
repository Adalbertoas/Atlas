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

/* Si ya había un token guardado, entrar directo sin pedir contraseña de nuevo. */
if (TOKEN) enterApp();

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
// Umbral del pellizco como fracción del tamaño de la mano (muñeca→nudillo medio),
// no como distancia fija — así funciona igual sin importar qué tan cerca de la
// cámara esté la mano (una distancia normalizada fija era muy estricta cuando
// la mano estaba lejos, porque todo se achica junto con ella).
const PINCH_RATIO = 0.55;
const CURLED_RATIO = 0.9; // qué tan más cerca de la muñeca debe estar la punta que el nudillo (dedo doblado = puño)

let scrollPrevY = null; // posición anterior del gesto de scroll, para calcular el delta entre frames

const gesturesVideo = document.getElementById("gestures-video");
const gesturesCanvas = document.getElementById("gestures-canvas");
const gesturesCtx = gesturesCanvas.getContext("2d");
const gesturesStatus = document.getElementById("gestures-status");
const gesturesToggle = document.getElementById("gestures-toggle");

let gesturesActive = false;
let gesturesStream = null;
let gesturesSocket = null;
let handLandmarker = null;
let gesturesRafId = null;

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
    await loadHandLandmarker();
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
  gesturesStatus.textContent = "Buscando tu mano…";
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
  gesturesCtx.clearRect(0, 0, gesturesCanvas.width, gesturesCanvas.height);
  gesturesStatus.textContent = "Cámara apagada";
  gesturesToggle.textContent = "🖐️ Activar control por gestos";
}

function detectLoop() {
  if (!gesturesActive) return;
  gesturesRafId = requestAnimationFrame(detectLoop);
  if (!handLandmarker || gesturesVideo.readyState < 2) return;

  const result = handLandmarker.detectForVideo(gesturesVideo, performance.now());
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
        statusParts.push(pinching ? "Pellizco (clic)" : "Cursor");
        if (gesturesSocket && gesturesSocket.readyState === WebSocket.OPEN) {
          gesturesSocket.send(
            JSON.stringify({ x: 1 - cursorPoint.x, y: cursorPoint.y, pinching }) // 1-x: coherente con el espejado
          );
        }
      }
    }
    gesturesStatus.textContent = statusParts.join(" · ");
  } else {
    gesturesStatus.textContent = "Buscando tu mano…";
  }
  if (!sawScrollHand) scrollPrevY = null;
  gesturesCtx.restore();
}

gesturesToggle.addEventListener("click", () => {
  if (gesturesActive) stopGestures();
  else startGestures();
});

/* ---------- Service worker (PWA instalable) ---------- */

if ("serviceWorker" in navigator) {
  window.addEventListener("load", () => {
    navigator.serviceWorker.register("./sw.js").catch(() => {});
  });
}
