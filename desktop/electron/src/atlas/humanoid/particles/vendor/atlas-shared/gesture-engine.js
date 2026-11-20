/* Motor de gestos para los clientes web (dashboard con la webcam de la PC y
 * PWA con la cámara del celular).
 *
 * Recibe el resultado de MediaPipe HandLandmarker de cada frame y decide qué
 * mandar por el WebSocket de /api/v1/gestures/stream. Vive en shared/ por el
 * mismo motivo que wake-word.js: dos copias de esta lógica terminan
 * desincronizadas (ya pasó con los umbrales de pellizco).
 *
 * Mano derecha = cursor:
 *   nudillo del índice mueve · pulgar+índice = clic/arrastre ·
 *   pulgar+medio = clic derecho · mano abierta = cursor en pausa (para
 *   reacomodar la mano sin mover el mouse).
 * Mano izquierda = comandos:
 *   puño + mover = scroll · ✌️ = cambiar ventana · ☝️ = play/pausa ·
 *   👍 = subir volumen · 🤙 = bajar volumen · 🤘 = escritorio ·
 *   palma abierta deslizada = atrás/adelante.
 *
 * Las poses de comando tienen que sostenerse POSE_HOLD_MS antes de
 * dispararse, así pasar por una pose sin querer (al cerrar la mano, por
 * ejemplo) no ejecuta nada. Las acciones solo son nombres; el backend las
 * traduce con una lista cerrada (app/gestures/mouse_controller.py).
 */

// Umbrales calibrados en vivo en la PWA (fracción del tamaño de la mano).
const PINCH_RATIO = 0.55;
// Clic derecho (pulgar + medio) más estricto que el pellizco normal: al
// apuntar, el pulgar suele descansar sobre el medio doblado, y con 0.55 eso
// ya contaba como clic derecho.
const RIGHT_PINCH_RATIO = 0.3;
const CURLED_RATIO = 0.9;    // punta más cerca de la muñeca que la articulación media
const EXTENDED_RATIO = 1.2;  // punta claramente más lejos que la articulación media
const THUMB_OUT_RATIO = 0.6; // punta del pulgar lejos del nudillo del índice

const POSE_HOLD_MS = 350;
const REPEAT_EVERY_MS = 250; // volumen: se repite mientras se sostiene la pose
const SWIPE_WINDOW_MS = 350;
const SWIPE_MIN_DX = 0.18;
const SWIPE_COOLDOWN_MS = 800;

const COMMAND_POSES = {
  victory: { action: "switch_window", label: "✌️ Cambiar ventana", repeat: false },
  point: { action: "play_pause", label: "☝️ Play/Pausa", repeat: false },
  rock: { action: "show_desktop", label: "🤘 Escritorio", repeat: false },
  thumbs_up: { action: "volume_up", label: "👍 Volumen +", repeat: true },
  shaka: { action: "volume_down", label: "🤙 Volumen −", repeat: true },
};

export const GESTURE_LEGEND = [
  { hand: "Derecha", gesture: "Mover la mano", effect: "Mueve el cursor (sigue el nudillo del índice)" },
  { hand: "Derecha", gesture: "Pulgar + índice", effect: "Clic; mantenerlo arrastra; dos seguidos = doble clic" },
  { hand: "Derecha", gesture: "Pulgar + medio", effect: "Clic derecho" },
  { hand: "Derecha", gesture: "Mano abierta", effect: "Pausa el cursor para reacomodar la mano" },
  { hand: "Izquierda", gesture: "✊ Puño + subir/bajar", effect: "Scroll" },
  { hand: "Izquierda", gesture: "✌️ V", effect: "Cambiar de ventana (Alt+Tab)" },
  { hand: "Izquierda", gesture: "☝️ Solo índice", effect: "Reproducir / pausar" },
  { hand: "Izquierda", gesture: "👍 Pulgar arriba", effect: "Subir volumen (sostener)" },
  { hand: "Izquierda", gesture: "🤙 Pulgar + meñique", effect: "Bajar volumen (sostener)" },
  { hand: "Izquierda", gesture: "🤘 Índice + meñique", effect: "Mostrar escritorio" },
  { hand: "Izquierda", gesture: "🖐️ Deslizar a un lado", effect: "Atrás / adelante" },
];

const dist = (a, b) => Math.hypot(a.x - b.x, a.y - b.y);

/** Qué dedos están extendidos o doblados. Todo relativo al tamaño de la
 *  mano, así funciona igual cerca o lejos de la cámara. */
export function readFingers(hand) {
  const wrist = hand[0];
  const handSize = dist(wrist, hand[9]); // muñeca → nudillo medio
  const finger = (tip, pip) => {
    const tipD = dist(hand[tip], wrist);
    const pipD = dist(hand[pip], wrist);
    return { extended: tipD > pipD * EXTENDED_RATIO, curled: tipD < pipD * CURLED_RATIO };
  };
  return {
    handSize,
    thumbOut: dist(hand[4], hand[5]) > handSize * THUMB_OUT_RATIO,
    index: finger(8, 6),
    middle: finger(12, 10),
    ring: finger(16, 14),
    pinky: finger(20, 18),
  };
}

/** Pose de la mano de comandos, o null si no es ninguna conocida. */
export function classifyPose(hand) {
  const f = readFingers(hand);
  const { index: i, middle: m, ring: r, pinky: p } = f;
  if (i.extended && m.extended && r.extended && p.extended) return "open";
  if (i.curled && m.curled && r.curled && p.curled) return f.thumbOut ? "thumbs_up" : "fist";
  if (i.extended && m.extended && r.curled && p.curled) return "victory";
  if (i.extended && m.curled && r.curled && p.extended) return "rock";
  if (i.extended && m.curled && r.curled && p.curled) return "point";
  if (f.thumbOut && i.curled && m.curled && r.curled && p.extended) return "shaka";
  return null;
}

export class GestureEngine {
  /** send(obj): manda un mensaje por el WebSocket (el cliente decide si está abierto). */
  constructor({ send, now = () => performance.now() }) {
    this._send = send;
    this._now = now;
    this.reset();
  }

  reset() {
    this._scrollPrevY = null;
    this._pose = null;
    this._poseSince = 0;
    this._poseFiredAt = null;
    this._palmTrail = [];
    this._lastSwipeAt = -Infinity;
    this._rightClickArmed = true;
    this._leftDown = false;
    this._lastCursor = null;
  }

  /** Procesa un frame de HandLandmarker. Devuelve un texto de estado. */
  process(result) {
    const parts = [];
    let sawCommandHand = false;
    let sawCursorHand = false;
    const hands = (result && result.landmarks) || [];

    for (let i = 0; i < hands.length; i++) {
      const hand = hands[i];
      // Clasificación sobre el frame crudo (sin espejar): "Left" es la mano
      // de comandos, igual que ya estaba calibrado.
      const handedness = result.handedness && result.handedness[i] && result.handedness[i][0];
      const isCommandHand = handedness && handedness.categoryName === "Left";
      if (isCommandHand) {
        sawCommandHand = true;
        parts.push(this._commandHand(hand));
      } else {
        sawCursorHand = true;
        parts.push(this._cursorHand(hand));
      }
    }

    if (!sawCommandHand) this._resetCommandHand();
    if (!sawCursorHand) this._releaseLeftClick();
    return parts.length ? parts.join(" · ") : "Buscando tu mano…";
  }

  _cursorHand(hand) {
    const f = readFingers(hand);
    const cursorPoint = hand[5]; // nudillo del índice: casi no se mueve al pellizcar
    const x = 1 - cursorPoint.x; // espejado, coherente con lo que se dibuja
    const y = cursorPoint.y;

    const openPalm = f.thumbOut && f.index.extended && f.middle.extended && f.ring.extended && f.pinky.extended;
    if (openPalm) {
      this._releaseLeftClick();
      this._rightClickArmed = true;
      return "Cursor en pausa";
    }

    const indexGap = dist(hand[8], hand[4]);
    const middleGap = dist(hand[12], hand[4]);
    const threshold = f.handSize * PINCH_RATIO;
    const indexPinch = indexGap < threshold && indexGap <= middleGap;
    const middlePinch =
      f.index.extended && middleGap < f.handSize * RIGHT_PINCH_RATIO && middleGap < indexGap;

    this._lastCursor = { x, y };
    this._send({ x, y, pinching: indexPinch });
    this._leftDown = indexPinch;

    if (middlePinch) {
      if (this._rightClickArmed) {
        this._send({ action: "right_click" });
        this._rightClickArmed = false;
      }
      return "Clic derecho";
    }
    this._rightClickArmed = true;
    return indexPinch ? "Pellizco (clic)" : "Cursor";
  }

  _releaseLeftClick() {
    // Nunca dejar el botón apretado si la mano desaparece o se abre a mitad de un arrastre.
    if (this._leftDown && this._lastCursor) {
      this._send({ ...this._lastCursor, pinching: false });
    }
    this._leftDown = false;
  }

  _commandHand(hand) {
    const pose = classifyPose(hand);
    const now = this._now();

    if (pose !== "fist") this._scrollPrevY = null;
    if (pose !== "open") this._palmTrail = [];

    if (pose === "fist") {
      this._setPose(pose, now);
      const palmY = (hand[0].y + hand[9].y) / 2;
      if (this._scrollPrevY !== null) this._send({ scroll: this._scrollPrevY - palmY });
      this._scrollPrevY = palmY;
      return "✊ Scroll";
    }

    if (pose === "open") {
      this._setPose(pose, now);
      return this._trackSwipe(hand, now);
    }

    const command = COMMAND_POSES[pose];
    if (!command) {
      this._setPose(null, now);
      return "Mano de comandos";
    }

    this._setPose(pose, now);
    const held = now - this._poseSince;
    if (held < POSE_HOLD_MS) return `${command.label}…`;

    const due =
      this._poseFiredAt === null || (command.repeat && now - this._poseFiredAt >= REPEAT_EVERY_MS);
    if (due) {
      this._send({ action: command.action });
      this._poseFiredAt = now;
    }
    return command.label;
  }

  _trackSwipe(hand, now) {
    const palmX = 1 - (hand[0].x + hand[9].x) / 2; // espejado: tu derecha real = +x
    this._palmTrail.push({ x: palmX, t: now });
    this._palmTrail = this._palmTrail.filter((p) => now - p.t <= SWIPE_WINDOW_MS);

    if (now - this._lastSwipeAt < SWIPE_COOLDOWN_MS) return "🖐️ Deslizar";
    const dx = palmX - this._palmTrail[0].x;
    if (Math.abs(dx) >= SWIPE_MIN_DX) {
      this._send({ action: dx > 0 ? "forward" : "back" });
      this._lastSwipeAt = now;
      this._palmTrail = [];
      return dx > 0 ? "🖐️ Adelante" : "🖐️ Atrás";
    }
    return "🖐️ Deslizar";
  }

  _setPose(pose, now) {
    if (pose !== this._pose) {
      this._pose = pose;
      this._poseSince = now;
      this._poseFiredAt = null;
    }
  }

  _resetCommandHand() {
    this._scrollPrevY = null;
    this._palmTrail = [];
    this._setPose(null, this._now());
  }
}
