// ATLAS Fase 5F — estado de voz del humanoide: idle, listening, thinking, executing, speaking, error.
// Es el ÚNICO punto que cambia el estado visual. Quien lo llama decide cuándo (el dashboard de ATLAS, VoiceSession del
// laboratorio u otro proveedor): este controlador nunca inventa un estado. Al cambiar de estado:
//   · núcleo (5E) → preset visual del estado;
//   · cuerpo (5C) → clip de reposo del estado (misma idea que Atlas3D del dashboard: error deja el cuerpo en Idle);
//   · audio real → nivel del núcleo y, al hablar, un leve asentimiento de cabeza (capa aditiva) que sigue a la voz.
// Contrato idéntico al de Atlas3D: setState(state) y setAudioSamples(Uint8Array de getByteTimeDomainData, centro 128).
export const VOICE_STATES = ["idle", "listening", "thinking", "executing", "speaking", "error"];
export const DEFAULT_BODY_CLIPS = { idle: "Idle", listening: "Listening", thinking: "Thinking", executing: "Explaining", speaking: "Talking", error: "Idle" };

export class VoiceStateController extends EventTarget {
  /**
   * @param {{avatar: object, bodyClips?: object, speakingNod?: number, errorRecoverMs?: number|null, bodyFade?: number}} o
   *  errorRecoverMs: si se da, ERROR vuelve solo a IDLE tras ese tiempo (el dashboard ya lo hace a 1,8 s; por defecto no).
   */
  constructor({ avatar, bodyClips = DEFAULT_BODY_CLIPS, speakingNod = 0.35, errorRecoverMs = null, bodyFade = 0.5 } = {}) {
    super();
    Object.assign(this, { avatar, bodyClips: { ...DEFAULT_BODY_CLIPS, ...bodyClips }, speakingNod, errorRecoverMs, bodyFade });
    this.state = "idle"; this.since = 0; this.time = 0; this.level = 0; this.levelT = -1e9;
    this.history = [];
    this._loopSet = null; this._errorTimer = null; this._nod = 0;
  }

  /** Cambia el estado. Desconocido → idle (con aviso), igual que Atlas3D. */
  setState(state, { source = "api" } = {}) {
    let s = state;
    if (!VOICE_STATES.includes(s)) { console.warn(`[ATLAS voz] estado desconocido "${state}" → idle`); s = "idle"; }
    const prev = this.state;
    if (s === prev) return false;
    this.state = s; this.since = this.time;
    this.history.push({ t: +this.time.toFixed(3), de: prev, a: s, origen: source }); if (this.history.length > 200) this.history.shift();
    const A = this.avatar;
    A.state = s;
    A.core?.setState(s);
    // cuerpo: clip de reposo del estado (con bucle mientras dure el estado)
    const clip = this.bodyClips[s], anim = A.animation;
    if (anim && clip && anim.clips.has(clip)) {
      if (this._loopSet && this._loopSet !== clip) { anim.setLoop(this._loopSet, null); this._loopSet = null; }
      if (!anim.isLooping(clip)) { anim.setLoop(clip, true); this._loopSet = clip; }
      if (anim.baseClip !== clip || anim.currentName !== clip) anim.setBaseClip(clip, { play: true, fade: this.bodyFade });
    }
    clearTimeout(this._errorTimer);
    if (s === "error" && this.errorRecoverMs) this._errorTimer = setTimeout(() => { if (this.state === "error") this.setState("idle", { source: "recuperación automática" }); }, this.errorRecoverMs);
    this.dispatchEvent(new CustomEvent("statechange", { detail: { state: s, previous: prev, source } }));
    return true;
  }

  /** Muestras de un AnalyserNode (getByteTimeDomainData), el mismo formato que usa el dashboard. */
  setAudioSamples(samples) {
    if (!samples?.length) return;
    let peak = 0; for (let i = 0; i < samples.length; i++) { const v = Math.abs(samples[i] - 128) / 128; if (v > peak) peak = v; }
    this.setAmplitude(peak);
  }
  /** Nivel de audio real 0–1 (para fuentes que ya dan amplitud). */
  setAmplitude(level) {
    this.level = Math.max(0, Math.min(1, +level || 0)); this.levelT = this.time;
    this.avatar.audioLevel = this.level;
    this.avatar.core?.setAudioLevel(this.level, this.avatar.core.time);
  }

  /** Cada frame (lo llama AtlasParticleAvatar.update). */
  update(dt) {
    this.time += dt;
    const anim = this.avatar.animation; if (!anim) return;
    // asentimiento ligado a la voz: sólo hablando, con la envolvente real del núcleo (cae a 0 si no llega audio)
    const env = this.avatar.core ? this.avatar.core.audioLevel : (this.time - this.levelT < 0.25 ? this.level : 0);
    const target = this.state === "speaking" && this.speakingNod > 0 ? Math.min(1, env * 1.6) * this.speakingNod : 0;
    if (target > 0.01 || this._nod > 0.01) {
      anim.setLayer("Nodding", target, { mask: "head", fade: 0.25 });
      this._nod = target;
      if (target <= 0.01) { anim.clearLayer("Nodding", { fade: 0.4 }); this._nod = 0; }
    }
  }

  get timeInState() { return this.time - this.since; }
  dispose() { clearTimeout(this._errorTimer); }
}
