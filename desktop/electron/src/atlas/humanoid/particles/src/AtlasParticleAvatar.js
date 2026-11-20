// ATLAS Fase 5B–5G — fachada del humanoide de partículas.
// Misma forma que Atlas3D del dashboard (setState / setAudioSamples / dispose) para poder sustituir
// a ParticleHuman más adelante sin tocar app.js. En la 5B sólo funcionan carga, animación, gestos y calidad;
// setState y setAudioSamples quedan guardados y se conectarán en la 5F (VoiceStateController).
import { HumanoidParticleModel } from "./model/HumanoidParticleModel.js";
import { ParticleEngine } from "./engine/ParticleEngine.js";
import { AnimationController } from "./anim/AnimationController.js";
import { HandGestureController } from "./anim/HandGestureController.js";
import { PerformanceMonitor } from "./perf/PerformanceMonitor.js";
import { HandTracker } from "./interaction/HandTracker.js";
import { InteractionController } from "./interaction/InteractionController.js";
import { MediaPipeHandProvider } from "./interaction/providers/MediaPipeHandProvider.js";
import { SyntheticHandProvider } from "./interaction/providers/SyntheticHandProvider.js";
import { AtlasCore } from "./fx/AtlasCore.js";
import { VoiceStateController } from "./voice/VoiceStateController.js";
import { VoiceSession, EchoProcessor } from "./voice/VoiceSession.js";

export class AtlasParticleAvatar {
  /**
   * @param {{canvas?: HTMLCanvasElement, renderer?: import('../vendor/three.module.js').WebGLRenderer,
   *          glbUrl: string, dataUrl?: string, quality?: 'LOW'|'MEDIUM'|'HIGH', onProgress?: (m:string)=>void}} opts
   */
  static async create(opts) {
    const a = new AtlasParticleAvatar();
    a.model = await HumanoidParticleModel.load(opts);
    a.engine = new ParticleEngine({ model: a.model, canvas: opts.canvas, renderer: opts.renderer, quality: opts.quality || "MEDIUM" });
    a.animation = new AnimationController(a.model);
    a.gestures = new HandGestureController(a.model, a.animation);
    a.perf = new PerformanceMonitor();
    a.state = "idle";
    a.audioLevel = 0;
    a.time = 0;
    a.animation.play("Idle", { fade: 0 });
    // 5E: núcleo de energía en el pecho + bloom (automático: activo en MEDIUM/HIGH, apagado en LOW)
    if (opts.core !== false) {
      const chest = a.model.mesh.skeleton.bones.find(b => b.name === "DEF-spine003") || null;
      a.core = new AtlasCore({ quality: a.engine.quality, pixelScale: a.engine.pointUniforms.pixelScale, anchorBone: chest, bodyUniforms: a.engine.pointUniforms });
      a.engine.object3D.add(a.core.object3D);
    }
    // 5F: estado de voz (único punto que cambia el estado visual; contrato de Atlas3D)
    a.voice = new VoiceStateController({ avatar: a, ...(opts.voice || {}) });
    a.bloomMode = opts.bloom ?? "auto";
    a._applyBloom();
    return a;
  }

  get object3D() { return this.engine.object3D; }

  /** Avanza animación y gestos y recalcula las partículas en la GPU. */
  update(dt) {
    this.voiceSession?.tick();     // 5F: audio real (micrófono o respuesta) → nivel
    this.voice?.update(dt);        // 5F: asentimiento ligado a la voz
    this.interaction?.update();    // 5D: gestos sostenidos de las manos del usuario → órdenes
    this.gestures.update(dt);      // primero los gestos: fijan el factor de dedos de este mismo frame
    this.animation.update(dt);     // pesos normalizados + mixer (sólo huesos, en CPU)
    this.engine.computeSkin();     // partículas en GPU con la boneTexture recién actualizada
    this.time += dt;
    this.core?.update(dt);         // 5E: núcleo (sigue al hueso del pecho ya actualizado)
  }

  render(scene, camera) { this.engine.render(scene, camera); this.perf.frame(); }

  playClip(name, opts) { this.animation.play(name, opts); }
  pause() { this.animation.pause(); }
  resume() { this.animation.resume(); }
  stopClip(opts) { this.animation.stop(opts); }
  setSpeed(s) { this.animation.setSpeed(s); }
  setLayer(name, weight, opts) { this.animation.setLayer(name, weight, opts); }
  clearLayer(name, opts) { this.animation.clearLayer(name, opts); }
  setGesture(side, gesture, opts) { this.gestures.set(side, gesture, opts); }
  releaseGesture(side, opts) { this.gestures.release(side, opts); }

  // --- 5D: entrada de manos (cámara con MediaPipe o proveedor sintético) ---
  /**
   * @param {{provider?: "mediapipe"|"synthetic"|object, mapping?: object, tracker?: object, mediapipe?: object}} [o]
   * @returns {Promise<{ok: boolean, status: string, message?: string}>}  nunca lanza: sin cámara el avatar sigue igual.
   */
  async enableHandInput({ provider = "mediapipe", mapping, tracker, mediapipe } = {}) {
    this.disableHandInput();
    this.handTracker = new HandTracker(tracker);
    this.interaction = new InteractionController({ avatar: this, tracker: this.handTracker, mapping });
    const onResult = (r, t) => this.handTracker.process(r, t);
    this.handProvider = provider === "mediapipe" ? new MediaPipeHandProvider({ onResult, ...mediapipe })
      : provider === "synthetic" ? new SyntheticHandProvider({ onResult }) : provider;
    if (this.handProvider && !this.handProvider.onResult) this.handProvider.onResult = onResult;
    try {
      const ok = await this.handProvider.start();
      const status = this.handProvider.status || (ok === false ? "error" : "running");
      return { ok: ok !== false, status, message: this.handProvider.lastMessage };
    } catch (err) {
      return { ok: false, status: "error", message: err.message };
    }
  }
  disableHandInput() {
    this.handProvider?.dispose?.(); this.interaction?.dispose(); this.handTracker?.reset();
    this.handProvider = this.interaction = this.handTracker = null;
  }
  setQuality(q) { this.engine.setQuality(q); this.core?.setQuality(q); this._applyBloom(); }

  // --- 5E: núcleo y efectos ---
  /** "auto" (MEDIUM/HIGH sí, LOW no) | "on" | "off". */
  setBloom(mode = "auto", opts) { this.bloomMode = mode === true ? "on" : mode === false ? "off" : mode; this._applyBloom(opts); }
  _applyBloom(opts) {
    if (!this.engine.ownsRenderer) return;          // con renderer del anfitrión, el postprocesado es cosa suya
    const on = this.bloomMode === "on" || (this.bloomMode === "auto" && this.engine.quality !== "LOW");
    this.engine.setBloom(on, opts);
  }
  setCoreControls(c) { this.core?.setControls(c); }
  setCoreVisible(on) { this.core?.setVisible(on); }

  // --- interfaz compatible con Atlas3D del dashboard (5F) ---
  setState(state, opts) { if (this.voice) this.voice.setState(state || "idle", opts); else { this.state = state || "idle"; this.core?.setState(this.state); } }
  setAudioSamples(samples) {
    if (this.voice) return this.voice.setAudioSamples(samples);
    if (!samples?.length) return;
    let peak = 0; for (const s of samples) peak = Math.max(peak, Math.abs(s - 128) / 128);
    this.audioLevel = peak; this.core?.setAudioLevel(peak, this.core.time);
  }
  setAmplitude(level) { this.voice?.setAmplitude(level); }

  /** 5F: ciclo de voz completo con micrófono y un procesador (por defecto el de PRUEBA, que devuelve tu voz). */
  startVoiceSession({ processor = new EchoProcessor(), ...o } = {}) {
    this.voiceSession?.dispose();
    this.voiceSession = new VoiceSession({ voice: this.voice, processor, ...o });
    return this.voiceSession;
  }
  stopVoiceSession() { this.voiceSession?.dispose(); this.voiceSession = null; this.voice?.setState("idle", { source: "sesión cerrada" }); }

  dispose() {
    this.disableHandInput();
    this.voiceSession?.dispose(); this.voiceSession = null; this.voice?.dispose(); this.voice = null;
    this.core?.dispose(); this.core = null;
    this.gestures?.dispose(); this.animation?.dispose(); this.engine?.dispose(); this.model?.dispose();
    this.gestures = this.animation = this.engine = this.model = null;
  }
}
