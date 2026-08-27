"use strict";

import { WakeWordEngine } from "/shared/wake-word.js";
import { renderMarkdown } from "/shared/markdown.js";

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
  loadWakeWord();
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

/* El arranque con sesión guardada NO va acá: enterApp() llama a
   loadWakeWord(), que usa wakeEngine — declarado más abajo. A esta
   altura está en la zona muerta temporal y tira "Cannot access
   'wakeEngine' before initialization", dejando la página muerta.
   Se llama al final del archivo. */

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
  // Solo las respuestas de ATLAS vienen en Markdown; lo que escribe el
  // usuario se muestra literal. renderMarkdown escapa el HTML por dentro.
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

async function sendChat(message) {
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
    // respondía mudo y parecía que la voz fallaba al azar — en realidad
    // dependía de QUÉ se pedía, no de cuándo.
    if (result.reply) speak(result.reply);
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
  let spoke = false;
  try {
    const result = await api("/api/v1/voice/transcribe", { method: "POST", body: form });
    if (result.text && result.text.trim()) {
      spoke = true; // sendChat dispara speak(), que reanuda la escucha al terminar
      await sendChat(result.text);
    } else if (wakeEngine.isActive) {
      appendBubble("atlas", "(No entendí el comando, sigo atento.)");
    }
  } catch (err) {
    appendBubble("atlas", `(error transcribiendo: ${err.message})`);
  }
  if (!spoke) resumeWakeIfActive();
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

/* ---------- Reproducción de la voz de ATLAS ---------- */
/* Los navegadores móviles son mucho más estrictos que los de escritorio con
   el autoplay: el permiso nace de un toque del usuario y **caduca**. El
   permiso de tocar "Enviar" ya no vale cuando el audio llega, varios
   segundos después (respuesta de Claude + síntesis). Resultado: en el
   celular no sonaba casi nunca.

   La solución estándar es no crear un `new Audio()` por respuesta, sino
   reutilizar SIEMPRE el mismo elemento y "desbloquearlo" en el primer toque
   del usuario. Una vez desbloqueado, se le puede cambiar el `src` y
   reproducir sin gesto nuevo. */

const speechAudio = new Audio();
speechAudio.preload = "auto";
// Dentro del DOM y no suelto: algunos navegadores móviles solo reproducen
// de forma confiable elementos que están en el documento.
speechAudio.hidden = true;
document.body.appendChild(speechAudio);
let audioUnlocked = false;

function unlockAudio() {
  if (audioUnlocked) return;
  // Un WAV mínimo y silencioso: alcanza para que el navegador marque el
  // elemento como autorizado por el usuario.
  speechAudio.src =
    "data:audio/wav;base64,UklGRiQAAABXQVZFZm10IBAAAAABAAEARKwAAIhYAQACABAAZGF0YQAAAAA=";
  speechAudio.play().then(() => {
    speechAudio.pause();
    speechAudio.currentTime = 0;
    audioUnlocked = true;
  }).catch(() => {
    /* se reintenta en el próximo toque */
  });
}
// `once: false`: si el primer intento falla (algunos navegadores exigen que
// el gesto sea sobre un control real), se vuelve a probar en el siguiente.
document.addEventListener("pointerdown", unlockAudio);
document.addEventListener("touchstart", unlockAudio);
document.addEventListener("keydown", unlockAudio);

async function speak(text) {
  try {
    const response = await api("/api/v1/voice/speak", { method: "POST", body: JSON.stringify({ text }) });
    const blob = await response.blob();

    // La escucha continua se reanuda recién cuando ATLAS terminó de hablar:
    // mientras suena, su propia voz por el parlante volvería a dispararla.
    speechAudio.onended = resumeWakeIfActive;
    speechAudio.onerror = resumeWakeIfActive;
    speechAudio.src = URL.createObjectURL(blob);

    try {
      await speechAudio.play();
    } catch (err) {
      // Si ni así deja, el texto ya se mostró — pero hay que decirlo: en
      // silencio parece que ATLAS ignoró el pedido.
      appendBubble("atlas", `(No pude reproducir el audio: ${err.message}. Tocá la pantalla y volvé a pedirlo.)`);
      resumeWakeIfActive();
    }
  } catch {
    /* la respuesta de texto ya se mostró; el audio es un extra */
    resumeWakeIfActive();
  }
}

/* ---------- Shazam (Fase 10: reconocimiento de canciones, vía AudD) ---------- */

const shazamButton = document.getElementById("shazam-button");
const SHAZAM_RECORD_MS = 6000; // AudD recomienda 3-10s de audio para reconocer bien

shazamButton.addEventListener("click", async () => {
  if (shazamButton.disabled) return;
  try {
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    const chunks = [];
    const recorder = new MediaRecorder(stream);
    recorder.ondataavailable = (e) => chunks.push(e.data);
    recorder.onstop = async () => {
      stream.getTracks().forEach((track) => track.stop());
      shazamButton.classList.remove("recording");
      const blob = new Blob(chunks, { type: recorder.mimeType || "audio/webm" });
      await identifySong(blob);
    };
    recorder.start();
    shazamButton.classList.add("recording");
    shazamButton.disabled = true;
    appendBubble("user", "🎵 (escuchando la canción...)");
    setTimeout(() => recorder.stop(), SHAZAM_RECORD_MS);
  } catch (err) {
    appendBubble("atlas", `(no pude acceder al micrófono: ${err.message})`);
  }
});

async function identifySong(blob) {
  const form = new FormData();
  form.append("audio", blob, "audio.webm");
  try {
    const result = await api("/api/v1/music/identify", { method: "POST", body: form });
    if (!result.found) {
      appendBubble("atlas", "No reconocí ninguna canción — probá de nuevo con más volumen.");
    } else {
      let reply = `🎵 ${result.title} — ${result.artist}`;
      if (result.album) reply += ` (${result.album})`;
      if (result.song_link) reply += `\n${result.song_link}`;
      appendBubble("atlas", reply);
    }
  } catch (err) {
    appendBubble("atlas", `(error reconociendo la canción: ${err.message})`);
  } finally {
    shazamButton.disabled = false;
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

/* ---------- Escucha continua (wake word) ---------- */
/* Mismo motor que el dashboard (shared/wake-word.js) y misma estrategia que
   el cliente de escritorio: buffer deslizante + filtro de energía local +
   Whisper. Apagado por defecto: mantiene el micrófono abierto de forma
   continua, y en un celular eso además consume batería, así que tiene que
   ser una decisión explícita. */

const wakeButton = document.getElementById("wake-button");
// Valor de respaldo: el real lo define el backend (ATLAS_WAKE_WORD), para
// que escritorio, dashboard y PWA no puedan quedar con palabras distintas.
let WAKE_WORD = "ali";

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
      wakeButton.classList.remove("active");
    }
  },
});

async function loadWakeWord() {
  try {
    const profile = await api("/api/v1/settings/profile");
    WAKE_WORD = profile.wake_word || WAKE_WORD;
    wakeEngine._wakeWord = WAKE_WORD;
  } catch {
    /* se queda con el valor de respaldo */
  }
  wakeButton.title = `Escucha continua: decí "${WAKE_WORD}" sin tocar nada`;
}

function resumeWakeIfActive() {
  if (wakeEngine.isActive) wakeEngine.resume();
}

wakeButton.addEventListener("click", async () => {
  if (wakeEngine.isActive) {
    wakeEngine.stop();
    wakeButton.classList.remove("active");
    return;
  }
  await wakeEngine.start();
  wakeButton.classList.toggle("active", wakeEngine.isActive);
  if (wakeEngine.isActive) {
    appendBubble("atlas", `(Escucha continua activada — decí "${WAKE_WORD}".)`);
  }
});

/* Al detectar la palabra: pausar la escucha (si no, ATLAS se oye a sí mismo
   por el parlante y se vuelve a disparar), grabar el comando cortando por
   silencio, y reanudar. Mismo criterio que el cliente de escritorio. */
const COMMAND_MAX_MS = 9000;
const COMMAND_SILENCE_MS = 1600;

async function onWakeWordDetected() {
  wakeEngine.pause();
  document.querySelector('.tab-button[data-view="chat"]').click();
  appendBubble("atlas", "(Te escuché — decime qué necesitás.)");

  let stream;
  try {
    stream = await navigator.mediaDevices.getUserMedia({ audio: true });
  } catch (err) {
    appendBubble("atlas", `(no pude acceder al micrófono: ${err.message})`);
    resumeWakeIfActive();
    return;
  }

  // Detección de silencio con Web Audio, para cortar solo: tras el wake word
  // nadie va a tocar "detener".
  const context = new (window.AudioContext || window.webkitAudioContext)();
  const analyser = context.createAnalyser();
  analyser.fftSize = 512;
  context.createMediaStreamSource(stream).connect(analyser);
  const samples = new Uint8Array(analyser.frequencyBinCount);

  const chunks = [];
  const recorder = new MediaRecorder(stream);
  recorder.ondataavailable = (e) => chunks.push(e.data);
  recorder.onstop = async () => {
    stream.getTracks().forEach((t) => t.stop());
    context.close().catch(() => {});
    voiceButton.classList.remove("recording");
    await transcribeAndSend(new Blob(chunks, { type: recorder.mimeType || "audio/webm" }));
  };
  recorder.start();
  voiceButton.classList.add("recording");

  const startedAt = Date.now();
  let lastSpeechAt = Date.now();
  let heardSpeech = false;

  const watch = () => {
    if (recorder.state !== "recording") return;
    analyser.getByteTimeDomainData(samples);
    let peak = 0;
    for (let i = 0; i < samples.length; i++) {
      peak = Math.max(peak, Math.abs((samples[i] - 128) / 128));
    }
    if (peak >= 0.045) {
      heardSpeech = true;
      lastSpeechAt = Date.now();
    }
    // Solo corta por silencio si antes escuchó algo: si no, esperaría el tope
    // duro cuando la palabra se detectó por un falso positivo.
    const quietFor = Date.now() - lastSpeechAt;
    if (Date.now() - startedAt >= COMMAND_MAX_MS || (heardSpeech && quietFor >= COMMAND_SILENCE_MS)) {
      recorder.stop();
      return;
    }
    setTimeout(watch, 150);
  };
  setTimeout(watch, 400); // margen para que el usuario empiece a hablar
}

/* ---------- Service worker (PWA instalable) ---------- */

if ("serviceWorker" in navigator) {
  window.addEventListener("load", () => {
    navigator.serviceWorker.register("./sw.js").catch(() => {});
  });
}


/* ---------- Arranque ---------- */
/* Última línea a propósito: con sesión guardada esto entra directo a la
   app, y enterApp() toca constantes declaradas a lo largo de todo el
   módulo. El login manual no tiene el problema porque corre desde un
   evento, ya evaluado el módulo entero — por eso el bug solo aparecía
   al recargar estando ya logueado. */
if (TOKEN) enterApp();
