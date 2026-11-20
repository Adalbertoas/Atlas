// ATLAS Fase 5D — manos sintéticas en formato MediaPipe (21 landmarks) para pruebas y para el laboratorio sin cámara.
// La geometría base es la misma que usan las pruebas del motor de gestos del dashboard (shared/tests), ampliada con
// giro, escala, lado, palma hacia/desde la cámara, ruido gaussiano y mezcla entre gestos.
// NO es un detector: produce datos de entrada conocidos para comprobar HandTracker e InteractionController.

const FINGER_X = { index: 0.44, middle: 0.5, ring: 0.56, pinky: 0.62 };
const BASES = { index: 5, middle: 9, ring: 13, pinky: 17 };
const POSES = {
  Open: { ext: ["index", "middle", "ring", "pinky"], half: [], thumbOut: true },
  Relaxed: { ext: [], half: ["index", "middle", "ring", "pinky"], thumbOut: false },
  Fist: { ext: [], half: [], thumbOut: false },
  Point: { ext: ["index"], half: [], thumbOut: false },
  Pinch: { ext: ["middle", "ring", "pinky"], half: [], thumbOut: false, pinch: true },
};

/** Mano izquierda con la palma hacia la cámara, muñeca en (0.5, 0.8), coordenadas de imagen. */
function baseHand(gesture) {
  const P = POSES[gesture];
  if (!P) throw new Error(`Gesto sintético desconocido: ${gesture}`);
  const p = (x, y, z = 0) => ({ x, y, z });
  const h = new Array(21);
  h[0] = p(0.5, 0.8); h[1] = p(0.42, 0.75, -0.01); h[2] = p(0.38, 0.7, -0.02); h[3] = p(0.36, 0.65, -0.025);
  h[4] = P.thumbOut ? p(0.3, 0.55, -0.03) : p(0.44, 0.58, -0.03);
  for (const [name, b] of Object.entries(BASES)) {
    const x = FINGER_X[name];
    h[b] = p(x, 0.6); h[b + 1] = p(x, 0.5, -0.01); h[b + 2] = p(x, 0.45, -0.015);
    h[b + 3] = P.ext.includes(name) ? p(x, 0.38, -0.02) : P.half.includes(name) ? p(x, 0.5, -0.04) : p(x, 0.63, -0.03);
  }
  if (P.pinch) { h[8] = { ...h[4] }; h[7] = p(0.43, 0.5, -0.03); }
  return h;
}

export function mulberry32(seed) {
  let a = seed >>> 0;
  return () => { a = (a + 0x6D2B79F5) >>> 0; let t = a; t = Math.imul(t ^ (t >>> 15), t | 1); t ^= t + Math.imul(t ^ (t >>> 7), t | 61); return ((t ^ (t >>> 14)) >>> 0) / 4294967296; };
}
const gauss = rnd => Math.sqrt(-2 * Math.log(Math.max(1e-9, rnd()))) * Math.cos(2 * Math.PI * rnd());

/**
 * Mano sintética.
 * @param {{gesture?: string, blendTo?: string, blend?: number, side?: "L"|"R", facing?: "camera"|"away",
 *          x?: number, y?: number, scale?: number, rollDeg?: number, noise?: number, rnd?: () => number}} o
 *   x, y: posición de la muñeca en la imagen; noise: desviación típica del ruido (fracción de la imagen).
 */
export function syntheticHand({ gesture = "Open", blendTo = null, blend = 0, side = "R", facing = "camera", x = 0.5, y = 0.8, scale = 1, rollDeg = 0, noise = 0, rnd = Math.random } = {}) {
  let h = baseHand(gesture);
  if (blendTo && blend > 0) { const b = baseHand(blendTo); h = h.map((p, i) => ({ x: p.x + (b[i].x - p.x) * blend, y: p.y + (b[i].y - p.y) * blend, z: p.z + (b[i].z - p.z) * blend })); }
  const mirror = (side === "R") !== (facing === "away");     // la base es una izquierda con la palma a la cámara
  const r = rollDeg * Math.PI / 180, c = Math.cos(r), s = Math.sin(r);
  return h.map(p => {
    let lx = (p.x - 0.5) * (mirror ? -1 : 1), ly = p.y - 0.8;
    const rx = lx * c - ly * s, ry = lx * s + ly * c;
    return { x: x + rx * scale + (noise ? gauss(rnd) * noise : 0), y: y + ry * scale + (noise ? gauss(rnd) * noise : 0), z: p.z * scale };
  });
}

/** Resultado con el formato de HandLandmarker.detectForVideo. hands: [{side, ...opciones de syntheticHand}] */
export function syntheticResult(hands) {
  return {
    landmarks: hands.map(h => syntheticHand(h)),
    handedness: hands.map(h => [{ categoryName: h.side === "L" ? "Left" : "Right", score: 0.95 }]),
  };
}

/**
 * Proveedor de demostración: recorre un guion de gestos con movimiento y ruido, a `fps`, y entrega cada frame a `onResult`.
 * Útil en el laboratorio sin cámara. start()/stop().
 */
export class SyntheticHandProvider {
  constructor({ onResult, fps = 30, seed = 7, noise = 0.003 } = {}) {
    this.onResult = onResult; this.fps = fps; this.rnd = mulberry32(seed); this.noise = noise; this.timer = null; this.t0 = 0;
    this.script = [
      { t: 0, R: "Open", L: null }, { t: 2, R: "Open", wave: true }, { t: 4.5, R: "Point", L: "Relaxed" }, { t: 7, R: "Fist", L: "Open" },
      { t: 9.5, R: "Pinch", L: "Point" }, { t: 12, R: "Relaxed", L: null }, { t: 14, R: null, L: null }, { t: 16 },
    ];
    this.name = "sintético";
  }
  frameAt(sec) {
    const dur = this.script[this.script.length - 1].t, tt = sec % dur;
    let cur = this.script[0]; for (const s of this.script) if (s.t <= tt) cur = s;
    const hands = [];
    if (cur.R) hands.push({ side: "R", gesture: cur.R, x: 0.35 + (cur.wave ? 0.06 * Math.sin(tt * 9) : 0.02 * Math.sin(tt)), y: 0.75, rollDeg: cur.wave ? 15 * Math.sin(tt * 9) : 0, noise: this.noise, rnd: this.rnd });
    if (cur.L) hands.push({ side: "L", gesture: cur.L, x: 0.68, y: 0.78, noise: this.noise, rnd: this.rnd });
    return syntheticResult(hands);
  }
  start() {
    if (this.timer) return;
    this.t0 = performance.now();
    this.timer = setInterval(() => { const now = performance.now(); this.onResult?.(this.frameAt((now - this.t0) / 1000), now); }, 1000 / this.fps);
  }
  stop() { clearInterval(this.timer); this.timer = null; }
  dispose() { this.stop(); }
}
