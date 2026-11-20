// ATLAS Fase 5D — gestos de dedos independientes por mano (Open, Relaxed, Fist, Point, Pinch).
// Evolución del controlador de la 5B (copia intacta en legacy/HandGestureController5B.js). Misma API de la 5B
// (set, snap, update, apply, gestureNames, transition) más:
//   · intensidad por mano (0–1): el gesto ocupa esa fracción de los dedos y el resto sigue a la animación de cuerpo;
//   · velocidad por mano (duración de la transición);
//   · release(side): vuelta a los dedos naturales de la animación; relax(side): gesto Relaxed;
//   · transiciones con un resorte críticamente amortiguado (solución exacta, estable con cualquier dt):
//     la posición Y la velocidad de cada peso son continuas, también al interrumpir un gesto a mitad.
//     (La 5B usaba un acercamiento exponencial: la velocidad saltaba de 0 a su máximo en el primer frame.)
// Para cada mano se mantiene: peso(dedos del cuerpo) = 1 − Σ peso(gestos) ≥ 0, así nunca se mezcla con la pose de reposo.
// Usa los clips Hand_<gesto>_<L|R> del GLB tal cual.
import * as THREE from "../../vendor/three.module.js";
import { GESTURES } from "../model/HumanoidParticleModel.js";

const SIDES = ["L", "R"];
const SETTLE = 4.74;
export const MIN_TRANSITION = 0.15;   // s: más rápido que esto el gesto se ve como un salto (medido en la 5D); 0 = aplicar al instante   // ω·T con el que un resorte crítico llega al 95 % en T (igual criterio que la 5B: 95 % en `transition`)

export class HandGestureController extends EventTarget {
  constructor(model, animation, { transition = 0.25 } = {}) {
    super();
    this.animation = animation;
    this.transition = transition;               // valor por defecto para las dos manos (compatibilidad 5B)
    this.actions = { L: {}, R: {} };
    this.weights = { L: {}, R: {} };
    this.velocity = { L: {}, R: {} };
    this.target = { L: null, R: null };
    this.intensity = { L: 1, R: 1 };
    this.handTransition = { L: null, R: null }; // null = usar this.transition
    for (const [eng, esp] of Object.entries(GESTURES)) {
      for (const side of SIDES) {
        const clip = model.gltf.animations.find(a => a.name === `Hand_${esp}_${side}`);
        if (!clip) continue;
        const a = animation.mixer.clipAction(clip);
        a.setLoop(THREE.LoopRepeat, Infinity); a.play(); a.setEffectiveWeight(0);
        this.actions[side][eng] = a; this.weights[side][eng] = 0; this.velocity[side][eng] = 0;
      }
    }
  }

  get gestureNames() { return Object.keys(GESTURES); }

  /**
   * gesture: "Open" | "Relaxed" | "Fist" | "Point" | "Pinch" | null (dedos de la animación).
   * Opciones: intensity (0–1), transition (s). Interrumpir un gesto con otro es seguro en cualquier momento.
   */
  set(side, gesture, { intensity, transition } = {}) {
    if (!SIDES.includes(side)) throw new Error(`Mano desconocida: ${side}`);
    if (gesture && !this.actions[side][gesture]) throw new Error(`Gesto desconocido: ${gesture}`);
    if (intensity !== undefined) this.setIntensity(side, intensity);
    if (transition !== undefined) this.setTransition(side, transition);
    const prev = this.target[side];
    this.target[side] = gesture || null;
    if (prev !== this.target[side]) this.dispatchEvent(new CustomEvent("gesture", { detail: { side, gesture: this.target[side], previous: prev } }));
  }
  /** Vuelve a los dedos naturales de la animación de cuerpo. */
  release(side, opts) { this.set(side, null, opts); }
  /** Postura relajada explícita. */
  relax(side, opts) { this.set(side, "Relaxed", opts); }
  setIntensity(side, v) { this.intensity[side] = Math.max(0, Math.min(1, +v || 0)); }
  /** Duración (s) de las transiciones de esa mano; null vuelve al valor común. */
  setTransition(side, s) { this.handTransition[side] = s === null ? null : (+s <= 0 ? 0 : Math.max(MIN_TRANSITION, +s)); }
  /** Velocidad relativa (2 = el doble de rápido que la transición común). Limitada por MIN_TRANSITION. */
  setSpeed(side, mult) { this.setTransition(side, mult > 0 ? this.transition / mult : null); }
  transitionOf(side) { return this.handTransition[side] ?? this.transition; }

  /** Estado legible de una mano (UI y pruebas). */
  state(side) {
    const w = this.weights[side];
    const sum = Object.values(w).reduce((s, x) => s + x, 0);
    const settled = Object.keys(w).every(g => Math.abs(w[g] - this._goal(side, g)) < 1e-3 && Math.abs(this.velocity[side][g]) < 1e-2);
    return { gesture: this.target[side], intensity: this.intensity[side], transition: this.transitionOf(side), weights: { ...w }, fingersFromBody: Math.max(0, 1 - sum), settled };
  }

  _goal(side, g) { return this.target[side] === g ? this.intensity[side] : 0; }

  /** Aplica de inmediato, sin transición (pruebas). */
  snap() {
    for (const side of SIDES) for (const g of Object.keys(this.weights[side])) { this.weights[side][g] = this._goal(side, g); this.velocity[side][g] = 0; }
    this.apply();
  }

  update(dt) {
    for (const side of SIDES) {
      const T = this.transitionOf(side);
      const W = this.weights[side], V = this.velocity[side];
      if (T <= 0) { for (const g of Object.keys(W)) { W[g] = this._goal(side, g); V[g] = 0; } continue; }
      const w = SETTLE / T, e = Math.exp(-w * dt);
      let sum = 0;
      for (const g of Object.keys(W)) {
        // resorte crítico, solución exacta: x(t) = (x0 + (v0 + ω·x0)·t)·e^(−ωt), x = peso − objetivo
        const goal = this._goal(side, g), x0 = W[g] - goal, v0 = V[g];
        const c = v0 + w * x0;
        let x = (x0 + c * dt) * e, v = (v0 - w * c * dt) * e;
        if (Math.abs(x) < 1e-5 && Math.abs(v) < 1e-4) { x = 0; v = 0; }
        let nw = goal + x;
        if (nw < 0) { nw = 0; v = Math.max(0, v); } else if (nw > 1) { nw = 1; v = Math.min(0, v); }
        W[g] = nw; V[g] = v; sum += nw;
      }
      if (sum > 1) for (const g of Object.keys(W)) W[g] /= sum;   // nunca más de 1 entre todos los gestos
    }
    this.apply();
  }

  apply() {
    for (const side of SIDES) {
      let sum = 0;
      for (const [g, a] of Object.entries(this.actions[side])) {
        const w = this.weights[side][g];
        if (!a.isScheduled()) a.play();   // por si alguien detuvo el mixer entero
        a.setEffectiveWeight(w); sum += w;
      }
      const fingerWeight = Math.max(0, 1 - sum);
      if (this.animation.setFingerFactor) this.animation.setFingerFactor(side, fingerWeight);                 // controlador 5C
      else for (const grp of this.animation.groups.values()) grp.fingers[side].weight = fingerWeight; // controlador 5B (legacy)
    }
    this.animation._applyWeights?.();   // 5G: una vez para las dos manos (antes, una por mano)
  }

  dispose() { for (const side of SIDES) for (const a of Object.values(this.actions[side])) a.stop(); }
}
