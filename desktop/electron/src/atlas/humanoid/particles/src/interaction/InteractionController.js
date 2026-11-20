// ATLAS Fase 5D — convierte lo que detecta HandTracker en órdenes para el humanoide.
// Configurable (DEFAULT_MAPPING): qué gesto del usuario pone qué gesto en qué mano del avatar, y qué acciones de cuerpo
// disparan (p. ej. mano abierta sostenida o saludo → clip Waving, con enfriamiento).
// Reglas de seguridad:
//   · nunca deja un gesto activo: si la mano sale del campo de visión, se suelta (vuelta a los dedos naturales);
//   · los clips de cuerpo pasan por AnimationController (transición suave y vuelta al clip de reposo actual),
//     y sólo si el avatar está en un estado que lo permite (por defecto idle/listening: no interrumpe al hablar);
//   · no mueve brazos por IK: las manos sólo usan clips del GLB ya validados, así que no se crean nuevas
//     interpenetraciones con el cuerpo.
export const DEFAULT_MAPPING = {
  mirror: true,                               // mano derecha del usuario → mano izquierda del avatar (como un espejo)
  gestures: { Open: "Open", Relaxed: "Relaxed", Fist: "Fist", Point: "Point", Pinch: "Pinch" },
  relaxedReleases: false,                     // true: "Relaxed" del usuario devuelve los dedos a la animación
  intensity: 1,
  transition: 0.25,
  actions: {
    wave: { clip: "Waving", cooldownMs: 6000 },              // movimiento de saludo con la mano abierta
    openHold: { clip: "Waving", holdMs: 900, cooldownMs: 6000 },  // mano abierta sostenida
    pointHold: null,                                          // p. ej. { clip: "Pointing", holdMs: 800, cooldownMs: 5000 }
  },
  allowBodyActionsIn: ["idle", "listening"],
};

export class InteractionController extends EventTarget {
  /**
   * @param {{avatar: object, tracker: import('./HandTracker.js').HandTracker, mapping?: object}} o
   */
  constructor({ avatar, tracker, mapping = {} }) {
    super();
    this.avatar = avatar; this.tracker = tracker;
    this.mapping = { ...DEFAULT_MAPPING, ...mapping, gestures: { ...DEFAULT_MAPPING.gestures, ...(mapping.gestures || {}) }, actions: { ...DEFAULT_MAPPING.actions, ...(mapping.actions || {}) } };
    this.enabled = true;
    this.lastAction = new Map();
    this.holdSince = { L: null, R: null };
    this.log = [];
    this._on = {
      gesture: e => this._gesture(e.detail), leave: e => this._leave(e.detail), wave: e => this._wave(e.detail),
    };
    for (const [k, fn] of Object.entries(this._on)) tracker.addEventListener(k, fn);
  }

  /** Mano del avatar que corresponde a una mano del usuario. */
  avatarSide(userSide) { return this.mapping.mirror ? (userSide === "L" ? "R" : "L") : userSide; }

  setEnabled(on) {
    this.enabled = on;
    if (!on) for (const s of ["L", "R"]) this.avatar.gestures.release(s, { transition: this.mapping.transition });
  }

  _record(type, detail) {
    const e = { t: +(this._now() / 1000).toFixed(3), type, ...detail };
    this.log.push(e); if (this.log.length > 200) this.log.shift();
    this.dispatchEvent(new CustomEvent("command", { detail: e }));
  }

  _gesture({ side, gesture }) {
    if (!this.enabled) return;
    const aSide = this.avatarSide(side);
    const g = this.avatar.gestures;
    this.holdSince[side] = gesture ? this._now() : null;
    if (!gesture && !this.tracker.hands[side]?.present) return;     // ya se soltó en "leave"
    if (!gesture || (gesture === "Relaxed" && this.mapping.relaxedReleases)) { g.release(aSide, { transition: this.mapping.transition }); this._record("release", { side: aSide }); return; }
    const target = this.mapping.gestures[gesture];
    if (target === undefined) return;
    if (target === null) g.release(aSide, { transition: this.mapping.transition });
    else g.set(aSide, target, { intensity: this.mapping.intensity, transition: this.mapping.transition });
    this._record("gesture", { side: aSide, gesture: target, from: gesture });
  }

  _leave({ side }) {
    if (!this.enabled) return;
    const aSide = this.avatarSide(side);
    this.holdSince[side] = null;
    this.avatar.gestures.release(aSide, { transition: this.mapping.transition });   // no deja gestos colgados
    this._record("release", { side: aSide, reason: "fuera de cámara" });
  }

  /** Reloj del seguimiento (marca de tiempo del último frame procesado), para que todo use la misma base. */
  _now() { return this.tracker.lastT ?? performance.now(); }

  _bodyAction(name, spec, side) {
    if (!spec || !this.enabled) return false;
    const state = this.avatar.state || "idle";
    if (!this.mapping.allowBodyActionsIn.includes(state)) return false;
    const now = this._now(), last = this.lastAction.get(spec.clip) ?? -Infinity;
    if (now - last < (spec.cooldownMs ?? 0)) return false;
    this.lastAction.set(spec.clip, now);
    this.avatar.playClip(spec.clip, { fade: 0.4 });
    this._record("clip", { clip: spec.clip, by: name, side: this.avatarSide(side) });
    return true;
  }

  _wave({ side }) { this._bodyAction("wave", this.mapping.actions.wave, side); }

  /** Llamar una vez por frame: comprueba gestos sostenidos. */
  update(now = this._now()) {
    if (!this.enabled) return;
    for (const side of ["L", "R"]) {
      const H = this.tracker.hands[side];
      if (!H.present || this.holdSince[side] === null) continue;
      const held = now - this.holdSince[side];
      if (H.gesture === "Open" && this.mapping.actions.openHold && held >= this.mapping.actions.openHold.holdMs) this._bodyAction("openHold", this.mapping.actions.openHold, side);
      if (H.gesture === "Point" && this.mapping.actions.pointHold && held >= this.mapping.actions.pointHold.holdMs) this._bodyAction("pointHold", this.mapping.actions.pointHold, side);
    }
  }

  dispose() { for (const [k, fn] of Object.entries(this._on)) this.tracker.removeEventListener(k, fn); this.setEnabled(false); }
}
