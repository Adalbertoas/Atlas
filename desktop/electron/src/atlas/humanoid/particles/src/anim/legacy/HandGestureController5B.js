// COPIA CONSERVADA de la Fase 5B/5C (HandGestureController original) para pruebas de comparación. No se usa en producción.
// ATLAS Fase 5B (compatible con el controlador 5C) — gestos de dedos independientes del cuerpo (Open, Relaxed, Fist, Point, Pinch por mano).
// Usa los clips Hand_<gesto>_<L|R> del GLB tal cual. Para cada mano:
//   peso(dedos del clip de cuerpo) = 1 − Σ peso(gestos)   →   suma siempre 1 (no se mezcla con la pose de reposo).
// Las transiciones entre gestos (y la vuelta a "ninguno") se suavizan con una constante de tiempo.
import * as THREE from "../../../vendor/three.module.js";
import { GESTURES } from "../../model/HumanoidParticleModel.js";

export class HandGestureController5B {
  constructor(model, animation, { transition = 0.25 } = {}) {
    this.animation = animation;
    this.transition = transition;
    this.actions = { L: {}, R: {} };
    this.weights = { L: {}, R: {} };
    this.target = { L: null, R: null };
    for (const [eng, esp] of Object.entries(GESTURES)) {
      for (const side of ["L", "R"]) {
        const clip = model.gltf.animations.find(a => a.name === `Hand_${esp}_${side}`);
        if (!clip) continue;
        const a = animation.mixer.clipAction(clip);
        a.setLoop(THREE.LoopRepeat, Infinity); a.play(); a.setEffectiveWeight(0);
        this.actions[side][eng] = a; this.weights[side][eng] = 0;
      }
    }
  }

  get gestureNames() { return Object.keys(GESTURES); }

  /** gesture: "Open" | "Relaxed" | "Fist" | "Point" | "Pinch" | null (dedos de la animación). */
  set(side, gesture) {
    if (gesture && !this.actions[side][gesture]) throw new Error(`Gesto desconocido: ${gesture}`);
    this.target[side] = gesture || null;
  }

  /** Aplica de inmediato, sin transición (pruebas). */
  snap() { for (const side of ["L", "R"]) for (const g of Object.keys(this.weights[side])) this.weights[side][g] = this.target[side] === g ? 1 : 0; this.apply(); }

  update(dt) {
    const k = this.transition > 0 ? 1 - Math.exp(-dt / (this.transition / 3)) : 1;
    for (const side of ["L", "R"]) for (const g of Object.keys(this.weights[side])) {
      const goal = this.target[side] === g ? 1 : 0;
      let w = this.weights[side][g] + (goal - this.weights[side][g]) * k;
      if (Math.abs(w - goal) < 1e-3) w = goal;
      this.weights[side][g] = w;
    }
    this.apply();
  }

  apply() {
    for (const side of ["L", "R"]) {
      let sum = 0;
      for (const [g, a] of Object.entries(this.actions[side])) {
        const w = this.weights[side][g];
        if (!a.isScheduled()) a.play();   // por si alguien detuvo el mixer entero
        a.setEffectiveWeight(w); sum += w;
      }
      const fingerWeight = Math.max(0, 1 - sum);
      if (this.animation.setFingerFactor) { this.animation.setFingerFactor(side, fingerWeight); this.animation._applyWeights?.(); }   // controlador 5C
      else for (const grp of this.animation.groups.values()) grp.fingers[side].weight = fingerWeight; // controlador 5B (legacy)
    }
  }

  dispose() { for (const side of ["L", "R"]) for (const a of Object.values(this.actions[side])) a.stop(); }
}
