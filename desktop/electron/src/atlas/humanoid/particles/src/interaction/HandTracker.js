// ATLAS Fase 5D — seguimiento de manos a partir de resultados de MediaPipe HandLandmarker (o de un proveedor sintético).
// Entrada por frame: { landmarks: [[21 × {x,y,z}]], handedness: [[{categoryName, score}]] } en coordenadas de imagen (0–1).
// Salida por mano real del usuario ("L" / "R"): presencia, posición, orientación, dedos extendidos/flexionados, pinza,
// movimiento, gesto estable (Open/Relaxed/Fist/Point/Pinch) y eventos enter/leave/gesture/wave.
//
// Reutiliza la lectura de dedos del dashboard (vendor/atlas-shared/gesture-engine.js, copia idéntica de shared/ del
// repositorio ATLAS) para que los umbrales sean los mismos que ya se calibraron en vivo.
// Anti-temblor: filtro One Euro por landmark + histéresis en la pinza + el gesto debe mantenerse `holdMs` para cambiar.
// Pérdida de seguimiento: la mano se mantiene `lostGraceMs` con su último estado antes de emitir "leave" (sin parpadeos).
import { readFingers } from "../../vendor/atlas-shared/gesture-engine.js";
import { LandmarkFilter } from "./OneEuroFilter.js";

export const TRACKED_GESTURES = ["Open", "Relaxed", "Fist", "Point", "Pinch"];
const dist = (a, b) => Math.hypot(a.x - b.x, a.y - b.y);
const PALM = [0, 5, 9, 13, 17];

/** Gesto instantáneo (sin histéresis temporal) de una mano de 21 landmarks. */
export function classifyHandGesture(hand, { pinchOn = 0.3, wasPinch = false, pinchOff = 0.45 } = {}) {
  // Pinza más estricta que el clic del dashboard (0.55): aquí distingue "Pinch" de una mano relajada, que también acerca el pulgar al índice.
  const f = readFingers(hand);
  const pinchRatio = dist(hand[4], hand[8]) / Math.max(1e-6, f.handSize);
  const pinch = pinchRatio < (wasPinch ? pinchOff : pinchOn);
  const ext = [f.index.extended, f.middle.extended, f.ring.extended, f.pinky.extended];
  const curled = [f.index.curled, f.middle.curled, f.ring.curled, f.pinky.curled];
  let gesture;
  if (curled.every(Boolean)) gesture = "Fist";
  else if (pinch && !f.index.extended) gesture = "Pinch";          // índice doblado hacia el pulgar
  else if (ext.every(Boolean)) gesture = "Open";
  else if (f.index.extended && curled[1] && curled[2] && curled[3]) gesture = "Point";
  else if (pinch) gesture = "Pinch";
  else gesture = "Relaxed";
  return { gesture, fingers: f, pinchRatio, pinch };
}

class HandState {
  constructor(side, filterOpts) {
    this.side = side; this.filter = new LandmarkFilter(filterOpts);
    this.present = false; this.lastSeen = -Infinity; this.landmarks = null;
    this.gesture = null; this.candidate = null; this.candidateSince = 0; this.pinch = false;
    this.position = { x: 0.5, y: 0.5 }; this.velocity = { x: 0, y: 0 }; this.speed = 0;
    this.rollDeg = 0; this.palmNormal = { x: 0, y: 0, z: 1 }; this.facing = "unknown";
    this.extended = {}; this.curled = {}; this.pinchRatio = 1; this.score = 0;
    this.swing = []; this.waving = false; this.lastWaveAt = -Infinity;
  }
}

export class HandTracker extends EventTarget {
  /**
   * @param {{holdMs?: number, lostGraceMs?: number, swapHandedness?: boolean, filter?: object,
   *          waveMinAmplitude?: number, waveReversals?: number, waveWindowMs?: number}} o
   */
  constructor({ holdMs = 120, lostGraceMs = 300, swapHandedness = false, filter = { minCutoff: 1.2, beta: 0.02 },
    waveMinAmplitude = 0.035, waveReversals = 2, waveWindowMs = 1500, waveCooldownMs = 1500 } = {}) {
    super();
    Object.assign(this, { holdMs, lostGraceMs, swapHandedness, waveMinAmplitude, waveReversals, waveWindowMs, waveCooldownMs });
    this.hands = { L: new HandState("L", filter), R: new HandState("R", filter) };
    this.frames = 0; this.lastT = null;
  }

  /** Lado real del usuario a partir de la etiqueta de MediaPipe. */
  _side(label) {
    const s = label === "Left" ? "L" : label === "Right" ? "R" : null;
    if (!s) return null;
    return this.swapHandedness ? (s === "L" ? "R" : "L") : s;
  }

  /** Procesa un resultado de HandLandmarker. tMs: marca de tiempo en milisegundos. */
  process(result, tMs = performance.now()) {
    this.frames++; this.lastT = tMs;
    const t = tMs / 1000;
    const seen = new Set();
    const list = result?.landmarks || [];
    for (let i = 0; i < list.length; i++) {
      const raw = list[i];
      if (!raw || raw.length < 21) continue;
      const h = result.handedness?.[i]?.[0];
      let side = this._side(h?.categoryName);
      if (!side) continue;
      if (seen.has(side)) {                 // dos manos con la misma etiqueta: se asigna la otra por posición
        const other = side === "L" ? "R" : "L";
        if (seen.has(other)) continue;
        side = other;
      }
      seen.add(side);
      this._update(this.hands[side], raw, t, tMs, h?.score ?? 1);
    }
    for (const side of ["L", "R"]) {
      const H = this.hands[side];
      if (!seen.has(side) && H.present && tMs - H.lastSeen > this.lostGraceMs) {
        H.present = false; H.waving = false; H.swing = []; H.velocity = { x: 0, y: 0 }; H.speed = 0;
        const prev = H.gesture; H.gesture = null; H.candidate = null;
        this.dispatchEvent(new CustomEvent("leave", { detail: { side, previousGesture: prev } }));
        if (prev) this.dispatchEvent(new CustomEvent("gesture", { detail: { side, gesture: null, previous: prev } }));
      }
    }
    this.dispatchEvent(new CustomEvent("update", { detail: this.snapshot() }));
  }

  _update(H, raw, t, tMs, score) {
    const gap = tMs - H.lastSeen;
    if (!H.present) {
      if (gap > this.lostGraceMs) H.filter.reset();   // vuelve tras perderse: no suavizar desde la posición antigua
      H.present = true;
      this.dispatchEvent(new CustomEvent("enter", { detail: { side: H.side } }));
    }
    H.lastSeen = tMs; H.score = score;
    const lm = H.filter.filter(raw, t);
    H.landmarks = lm;
    // posición (centro de la palma) y movimiento
    let px = 0, py = 0; for (const k of PALM) { px += lm[k].x; py += lm[k].y; } px /= PALM.length; py /= PALM.length;
    if (H._pt !== undefined && t > H._pt) {
      const dt = t - H._pt;
      H.velocity = { x: (px - H.position.x) / dt, y: (py - H.position.y) / dt };
      H.speed = Math.hypot(H.velocity.x, H.velocity.y);
    }
    H.position = { x: px, y: py }; H._pt = t;
    // orientación: giro en el plano de la imagen y normal de la palma (con la z relativa de MediaPipe)
    const up = { x: lm[9].x - lm[0].x, y: lm[9].y - lm[0].y };
    H.rollDeg = Math.atan2(up.x, -up.y) * 180 / Math.PI;     // 0° = dedos hacia arriba
    const a = { x: lm[5].x - lm[0].x, y: lm[5].y - lm[0].y, z: lm[5].z - lm[0].z };
    const b = { x: lm[17].x - lm[0].x, y: lm[17].y - lm[0].y, z: lm[17].z - lm[0].z };
    const n = { x: a.y * b.z - a.z * b.y, y: a.z * b.x - a.x * b.z, z: a.x * b.y - a.y * b.x };
    const nl = Math.hypot(n.x, n.y, n.z) || 1;
    H.palmNormal = { x: n.x / nl, y: n.y / nl, z: n.z / nl };
    const towardCamera = (H.side === "R" ? -1 : 1) * H.palmNormal.z;   // >0: palma hacia la cámara (convención de imagen sin espejar)
    H.facing = Math.abs(H.palmNormal.z) < 0.35 ? "side" : towardCamera > 0 ? "camera" : "away";
    // dedos y gesto
    const c = classifyHandGesture(lm, { wasPinch: H.pinch });
    H.pinch = c.pinch; H.pinchRatio = c.pinchRatio;
    for (const k of ["index", "middle", "ring", "pinky"]) { H.extended[k] = c.fingers[k].extended; H.curled[k] = c.fingers[k].curled; }
    H.extended.thumb = c.fingers.thumbOut; H.curled.thumb = !c.fingers.thumbOut;
    if (c.gesture !== H.candidate) { H.candidate = c.gesture; H.candidateSince = tMs; }
    if (H.candidate !== H.gesture && (tMs - H.candidateSince >= this.holdMs || H.gesture === null && this.holdMs === 0)) {
      const prev = H.gesture; H.gesture = H.candidate;
      this.dispatchEvent(new CustomEvent("gesture", { detail: { side: H.side, gesture: H.gesture, previous: prev } }));
    }
    // saludo: inversiones del movimiento horizontal con amplitud suficiente dentro de una ventana
    this._wave(H, px, tMs);
  }

  _wave(H, x, tMs) {
    const S = H.swing;
    if (!S.length) { S.push({ x, t: tMs, dir: 0, ext: x }); return; }
    const last = S[S.length - 1];
    const dir = Math.sign(x - last.ext);
    if (last.dir === 0) { if (Math.abs(x - last.ext) > this.waveMinAmplitude / 2) { last.dir = dir; last.ext = x; } }
    else if (dir === last.dir) last.ext = x;
    else if (Math.abs(x - last.ext) > this.waveMinAmplitude) S.push({ x, t: tMs, dir, ext: x });  // inversión
    while (S.length && tMs - S[0].t > this.waveWindowMs) S.shift();
    const reversals = Math.max(0, S.length - 1);
    H.waving = reversals >= this.waveReversals && H.gesture === "Open";
    if (H.waving && tMs - H.lastWaveAt > this.waveCooldownMs) {
      H.lastWaveAt = tMs;
      this.dispatchEvent(new CustomEvent("wave", { detail: { side: H.side } }));
    }
  }

  snapshot() {
    const out = {};
    for (const side of ["L", "R"]) {
      const H = this.hands[side];
      out[side] = { present: H.present, gesture: H.gesture, position: { ...H.position }, velocity: { ...H.velocity }, speed: +H.speed.toFixed(4),
        rollDeg: +H.rollDeg.toFixed(1), facing: H.facing, palmNormal: { ...H.palmNormal }, extended: { ...H.extended }, curled: { ...H.curled },
        pinch: H.pinch, pinchRatio: +H.pinchRatio.toFixed(3), waving: H.waving, score: H.score };
    }
    return out;
  }

  reset() { for (const side of ["L", "R"]) { const f = this.hands[side].filter; this.hands[side] = new HandState(side, {}); this.hands[side].filter = f; f.reset(); } }
}
