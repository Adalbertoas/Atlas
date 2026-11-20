// ATLAS Fase 5D — filtro One Euro (Casiez et al., CHI 2012) para suavizar landmarks sin añadir retraso al moverse rápido.
// Poco movimiento → corte bajo (quita el temblor); movimiento rápido → corte alto (sigue a la mano sin lag).
const alpha = (cutoff, dt) => { const tau = 1 / (2 * Math.PI * cutoff); return 1 / (1 + tau / dt); };

export class OneEuroFilter {
  constructor({ minCutoff = 1.2, beta = 0.02, dCutoff = 1.0 } = {}) {
    this.minCutoff = minCutoff; this.beta = beta; this.dCutoff = dCutoff;
    this.reset();
  }
  reset() { this.x = null; this.dx = 0; this.t = null; }
  /** value: número; t: segundos. */
  filter(value, t) {
    if (this.x === null || this.t === null || t <= this.t) { this.x = value; this.dx = 0; this.t = t; return value; }
    const dt = t - this.t; this.t = t;
    const dx = (value - this.x) / dt;
    this.dx += alpha(this.dCutoff, dt) * (dx - this.dx);
    const cutoff = this.minCutoff + this.beta * Math.abs(this.dx);
    this.x += alpha(cutoff, dt) * (value - this.x);
    return this.x;
  }
}

/** 21 landmarks × (x, y, z) filtrados de forma independiente. */
export class LandmarkFilter {
  constructor(opts) { this.f = Array.from({ length: 63 }, () => new OneEuroFilter(opts)); }
  reset() { for (const f of this.f) f.reset(); }
  filter(hand, t) {
    const out = new Array(21);
    for (let i = 0; i < 21; i++) {
      const p = hand[i];
      out[i] = { x: this.f[i * 3].filter(p.x, t), y: this.f[i * 3 + 1].filter(p.y, t), z: this.f[i * 3 + 2].filter(p.z ?? 0, t) };
    }
    return out;
  }
}
