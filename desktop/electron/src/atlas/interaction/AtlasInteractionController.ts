// Une cámara, audio, estados y preferencias con el motor de partículas.
// No depende de React: la interfaz se suscribe a `snapshot` y `live`.

import { AudioAnalyzer } from "../audio-reactive/AudioAnalyzer.ts";
import { VoiceVisualizer } from "../audio-reactive/VoiceVisualizer.ts";
import { gestureConfigFor } from "../hand-tracking/GestureConfig.ts";
import { GestureController } from "../hand-tracking/GestureController.ts";
import { GestureRecognizer } from "../hand-tracking/GestureRecognizer.ts";
import { HandTrackingService, type HandTrackingStatus, type InferenceDelegate } from "../hand-tracking/HandTrackingService.ts";
import { LandmarkSmoother } from "../hand-tracking/LandmarkSmoother.ts";
import type { GestureName, HandFrame, TrackedHand } from "../hand-tracking/types.ts";
import type { CoreInputs } from "../particle-core/ParticleAnimator.ts";
import { CORE_VIEW, ParticleCore, type CoreStats } from "../particle-core/ParticleCore.ts";
import { hexToRgb, nextLowerQuality, pickInitialQuality, VISUAL_PRESETS, type PresetName, type QualityLevel } from "../particle-core/ParticlePresets.ts";
import { VoiceSession, type VoicePhase, type VoiceTransport } from "../voice/VoiceSession.ts";
import { AtlasVisualStateMachine, type AtlasVisualState } from "./AtlasVisualStateMachine.ts";
import { SettingsStore, type NeuralCoreSettings, type SettingsStorage } from "./InteractionConfig.ts";

export type CoreStatus = "off" | "ok" | "unavailable" | "context-lost";

/** Estado de baja frecuencia: cambia con eventos, no con cada fotograma. */
export type RuntimeSnapshot = {
  state: AtlasVisualState;
  camera: HandTrackingStatus;
  voice: VoicePhase;
  core: CoreStatus;
  quality: QualityLevel;
  /** El rendimiento cayó de forma sostenida y hay una calidad inferior disponible. */
  performanceHint: boolean;
  notice: string | null;
};

/** Telemetría local para la interfaz (no sale de la aplicación). */
export type RuntimeLive = {
  stats: CoreStats | null;
  inferenceMs: number | null;
  handCount: number;
  activeGestures: readonly GestureName[];
};

export type ControllerOptions = {
  transport: VoiceTransport;
  storage: SettingsStorage | null;
  /** URL de la carpeta con los recursos locales de MediaPipe. */
  mediapipeBase: string;
  /** Orden de delegados de inferencia; por defecto el del servicio. */
  handDelegates?: InferenceDelegate[];
};

const SLEEP_AFTER_MS = 3 * 60 * 1000;
const SUCCESS_PULSE_MS = 1400;
const ERROR_PULSE_MS = 2600;
const INFERENCE_FPS = 20;
const IDLE_TICK_MS = 200;

class Store<T> {
  private readonly listeners = new Set<() => void>();
  private value: T;

  constructor(initial: T) {
    this.value = initial;
  }

  get = (): T => this.value;

  subscribe = (listener: () => void): (() => void) => {
    this.listeners.add(listener);
    return () => this.listeners.delete(listener);
  };

  patch(patch: Partial<T>): void {
    const keys = Object.keys(patch) as (keyof T)[];
    if (keys.every((key) => Object.is(this.value[key], patch[key]))) return;
    this.value = { ...this.value, ...patch };
    for (const listener of this.listeners) listener();
  }
}

export class AtlasInteractionController {
  readonly settings: SettingsStore;
  readonly snapshot: Store<RuntimeSnapshot>;
  readonly live = new Store<RuntimeLive>({ stats: null, inferenceMs: null, handCount: 0, activeGestures: [] });

  /** Texto transcrito listo para enviarse al chat. Lo asigna la interfaz. */
  onTranscript: ((text: string) => void) | null = null;
  /** Gesto de pinza confirmado, en coordenadas -1..1 del encuadre. */
  onSelect: ((point: { x: number; y: number }) => void) | null = null;

  /** Adaptador de los eventos reales del asistente. La interfaz lo invoca en el
      momento exacto en que ocurren; aquí no se simula ninguno. */
  readonly assistant = {
    requestStarted: (): void => {
      this.noteActivity();
      this.states.setSignal("THINKING", true);
      this.refresh();
    },
    requestSucceeded: (): void => {
      this.states.setSignal("THINKING", false);
      this.states.pulse("SUCCESS", SUCCESS_PULSE_MS, performance.now());
      this.refresh();
    },
    requestFailed: (): void => {
      this.states.setSignal("THINKING", false);
      this.states.pulse("ERROR", ERROR_PULSE_MS, performance.now());
      this.refresh();
    },
  };

  private readonly options: ControllerOptions;
  private readonly states = new AtlasVisualStateMachine();
  private readonly analyzer = new AudioAnalyzer();
  private readonly visualizer = new VoiceVisualizer();
  private readonly voice: VoiceSession;
  private readonly smoother = new LandmarkSmoother();
  private readonly recognizer: GestureRecognizer;
  private readonly gestures: GestureController;
  private readonly unsubscribe: (() => void)[] = [];
  private readonly idleTimer: number;
  private hands: HandTrackingService | null = null;
  private core: ParticleCore | null = null;
  private autoQuality: QualityLevel = "medium";
  private lastActivity = performance.now();
  private motionScale = 1;
  private glow = 1;
  private debugHands: TrackedHand[] = [];
  private inferenceMs = 0;
  private gestureKey = "";
  private lastInferenceReport = 0;
  private qualityProbed = false;

  constructor(options: ControllerOptions) {
    this.options = options;
    this.settings = new SettingsStore(options.storage);
    const initial = this.settings.get();
    this.snapshot = new Store<RuntimeSnapshot>({ state: "IDLE", camera: "off", voice: "idle", core: "off", quality: this.effectiveQuality(initial), performanceHint: false, notice: null });

    this.recognizer = new GestureRecognizer(gestureConfigFor(initial.gestureSensitivity));
    this.gestures = new GestureController({
      actions: {
        select: ({ point }) => {
          if (point) this.onSelect?.(point);
        },
        // Efecto puramente visual: no cierra ni destruye nada.
        explode: () => this.core?.triggerExplosion(),
        reconstruct: () => this.core?.reconstruct(),
      },
    });
    this.gestures.setEnabled(initial.gestures, initial.rotateWithHand);

    this.voice = new VoiceSession({
      analyzer: this.analyzer,
      transport: options.transport,
      onPhase: (phase) => this.handleVoicePhase(phase),
      onTranscript: (text) => this.onTranscript?.(text),
      onError: (message) => this.reportError(message),
    });

    this.unsubscribe.push(
      this.settings.subscribe(() => this.applySettings()),
      this.states.subscribe((state) => {
        if (state === "SUCCESS") this.core?.triggerPulse();
        this.snapshot.patch({ state });
      }),
    );
    // Mientras el núcleo no renderiza (desactivado o sin WebGL) los pulsos
    // temporales y el reposo siguen necesitando un reloj.
    this.idleTimer = window.setInterval(() => this.refresh(), IDLE_TICK_MS);
  }

  // ---------- Núcleo ----------

  /** Monta el motor sobre `canvas`. Devuelve la función que lo desmonta y
      libera sus recursos. Si WebGL no está disponible no lanza: lo refleja en
      `snapshot.core` y el resto de ATLAS sigue funcionando. */
  attachCore(canvas: HTMLCanvasElement): () => void {
    this.detachCore();
    const settings = this.settings.get();
    try {
      const core = new ParticleCore({
        canvas,
        quality: this.effectiveQuality(settings),
        bloom: settings.bloom,
        provideInputs: (dt, now) => this.provideInputs(dt, now),
        onStats: (stats) => this.live.patch({ stats }),
        onPerformanceDegraded: (quality) => this.handleDegradation(quality),
        onContextLost: () => this.snapshot.patch({ core: "context-lost" }),
        onContextRestored: () => this.snapshot.patch({ core: "ok" }),
        onError: (error) => {
          console.warn("[neural-core] El render fallo y el nucleo se detuvo:", error);
          this.snapshot.patch({ core: "unavailable" });
        },
      });
      this.core = core;
      // Solo la primera vez: si ya se redujo la calidad en esta sesión, volver
      // a montar la vista no debe subirla de nuevo.
      if (!this.qualityProbed) {
        this.qualityProbed = true;
        this.autoQuality = pickInitialQuality(core.rendererName);
      }
      core.setQuality(this.effectiveQuality(settings));
      core.start();
      this.snapshot.patch({ core: "ok", quality: this.effectiveQuality(settings), performanceHint: false });
    } catch (error) {
      console.warn("[neural-core] WebGL no disponible:", error);
      this.core = null;
      this.snapshot.patch({ core: "unavailable" });
    }
    return () => this.detachCore();
  }

  setViewAspect(aspect: number): void {
    this.gestures.setView({ aspect, halfHeight: CORE_VIEW.halfHeight, centerY: CORE_VIEW.centerY });
  }

  /** Preferencias globales de apariencia de ATLAS que el núcleo respeta. */
  setEnvironment(environment: { motion: boolean; glow: number }): void {
    this.motionScale = environment.motion ? 1 : 0;
    this.glow = Math.max(0.2, Math.min(1, environment.glow));
  }

  triggerPulse(): void {
    this.core?.triggerPulse();
  }

  /** Deshace los giros hechos con las manos. */
  resetOrientation(): void {
    this.gestures.resetOrientation();
  }

  triggerExplosion(): void {
    this.core?.triggerExplosion();
  }

  /** Acepta la sugerencia de rendimiento: baja un nivel de calidad. */
  lowerQuality(): void {
    const lower = nextLowerQuality(this.snapshot.get().quality);
    if (lower) this.settings.update({ quality: lower });
    this.snapshot.patch({ performanceHint: false });
  }

  // ---------- Voz ----------

  async toggleMicrophone(): Promise<void> {
    this.noteActivity();
    if (this.voice.recording) this.voice.stopRecording();
    else await this.voice.startRecording();
  }

  cancelMicrophone(): void {
    this.voice.cancelRecording();
  }

  speak(text: string): Promise<void> {
    return this.voice.speak(text);
  }

  stopSpeaking(): void {
    this.voice.stopSpeaking();
  }

  // ---------- Manos ----------

  /** Enciende la cámara. Solo debe llamarse tras una acción explícita del usuario. */
  async enableHandControl(): Promise<void> {
    this.noteActivity();
    await this.ensureHands().start();
  }

  disableHandControl(): void {
    this.hands?.stop();
  }

  /** Carga WASM y modelo sin encender la cámara (diagnóstico). */
  async preloadHandModel(): Promise<void> {
    await this.ensureHands().loadModel();
  }

  /** Datos para la vista de depuración opcional. */
  get debug(): { hands: readonly TrackedHand[]; video: HTMLVideoElement | null } {
    return { hands: this.debugHands, video: this.hands?.videoElement ?? null };
  }

  // ---------- General ----------

  noteActivity(): void {
    this.lastActivity = performance.now();
  }

  dismissNotice(): void {
    this.snapshot.patch({ notice: null });
  }

  dispose(): void {
    window.clearInterval(this.idleTimer);
    for (const unsubscribe of this.unsubscribe) unsubscribe();
    this.detachCore();
    this.hands?.dispose();
    this.hands = null;
    this.voice.dispose();
    this.analyzer.dispose();
  }

  // ---------- Interno ----------

  private ensureHands(): HandTrackingService {
    this.hands ??= new HandTrackingService({
      assetBase: this.options.mediapipeBase,
      inferenceFps: INFERENCE_FPS,
      delegates: this.options.handDelegates,
      onFrame: (frame, inferenceMs) => this.handleHandFrame(frame, inferenceMs),
      onStatus: (status, error) => this.handleCameraStatus(status, error),
    });
    return this.hands;
  }

  private detachCore(): void {
    if (!this.core) {
      if (this.snapshot.get().core !== "off") this.snapshot.patch({ core: "off" });
      return;
    }
    this.core.dispose();
    this.core = null;
    this.live.patch({ stats: null });
    this.snapshot.patch({ core: "off", performanceHint: false });
  }

  private effectiveQuality(settings: NeuralCoreSettings): QualityLevel {
    return settings.quality === "auto" ? this.autoQuality : settings.quality;
  }

  private applySettings(): void {
    const settings = this.settings.get();
    this.recognizer.setConfig(gestureConfigFor(settings.gestureSensitivity));
    this.gestures.setEnabled(settings.gestures, settings.rotateWithHand);
    if (!settings.voiceReaction) this.visualizer.reset();
    const quality = this.effectiveQuality(settings);
    this.core?.setQuality(quality);
    this.core?.setBloom(settings.bloom);
    this.snapshot.patch({ quality });
  }

  private handleDegradation(quality: QualityLevel): void {
    const settings = this.settings.get();
    const lower = nextLowerQuality(quality);
    if (!lower) return;
    if (settings.quality === "auto" && settings.autoReduceQuality) {
      this.autoQuality = lower;
      this.core?.setQuality(lower);
      this.snapshot.patch({ quality: lower, notice: `Rendimiento bajo: calidad grafica reducida a ${lower.toUpperCase()}.` });
    } else {
      // Con calidad fijada a mano solo se sugiere; decide el usuario.
      this.snapshot.patch({ performanceHint: true });
    }
  }

  private provideInputs(dt: number, now: number): CoreInputs {
    const state = this.refresh(now);
    const settings = this.settings.get();
    const raw = settings.voiceReaction ? this.analyzer.sample() : null;
    const audio = this.visualizer.update(raw, dt, now);
    const tint = state === "IDLE" && settings.coreColor ? hexToRgb(settings.coreColor) : null;
    return {
      preset: VISUAL_PRESETS[state.toLowerCase() as PresetName],
      gesture: this.gestures.step(dt),
      audio,
      intensity: settings.intensity * this.glow,
      energyEffects: settings.energyEffects,
      motionScale: this.motionScale,
      tint,
    };
  }

  private refresh(now = performance.now()): AtlasVisualState {
    this.states.setSignal("SLEEPING", now - this.lastActivity > SLEEP_AFTER_MS);
    return this.states.update(now);
  }

  private handleVoicePhase(phase: VoicePhase): void {
    this.noteActivity();
    this.states.setSignal("LISTENING", phase === "recording");
    this.states.setSignal("PROCESSING", phase === "transcribing" || phase === "synthesizing");
    this.states.setSignal("SPEAKING", phase === "speaking");
    this.snapshot.patch({ voice: phase });
    this.refresh();
  }

  private handleCameraStatus(status: HandTrackingStatus, error?: string): void {
    if (status !== "active") {
      this.gestures.release();
      this.recognizer.reset();
      this.smoother.reset();
      this.debugHands = [];
      this.gestureKey = "";
      this.live.patch({ inferenceMs: null, handCount: 0, activeGestures: [] });
    }
    this.snapshot.patch({ camera: status });
    if (status === "error") this.reportError(error ?? "Error de camara.");
  }

  private handleHandFrame(frame: HandFrame, inferenceMs: number): void {
    const keys: string[] = [];
    const hands = frame.hands.map((hand, index) => {
      // MediaPipe puede etiquetar dos manos con la misma lateralidad.
      let key = hand.handedness ?? `hand-${index}`;
      if (keys.includes(key)) key = `${key}-${index}`;
      keys.push(key);
      return { ...hand, landmarks: this.smoother.smooth(key, hand.landmarks, frame.timestamp) };
    });
    this.smoother.retain(keys);
    this.debugHands = hands;

    const output = this.recognizer.update({ timestamp: frame.timestamp, hands });
    this.gestures.ingest(output, frame.timestamp);
    if (output.tracked) this.noteActivity();

    this.inferenceMs += (inferenceMs - this.inferenceMs) * (this.inferenceMs ? 0.15 : 1);
    const active = [...output.active];
    const key = `${output.handCount}|${active.join(",")}`;
    if (key !== this.gestureKey) {
      this.gestureKey = key;
      this.live.patch({ handCount: output.handCount, activeGestures: active });
    }
    // La cifra de inferencia es informativa: publicarla a 2 Hz evita
    // re-renderizar la interfaz con cada fotograma de cámara.
    if (frame.timestamp - this.lastInferenceReport >= 500) {
      this.lastInferenceReport = frame.timestamp;
      this.live.patch({ inferenceMs: Math.round(this.inferenceMs * 10) / 10 });
    }
  }

  private reportError(message: string): void {
    this.states.pulse("ERROR", ERROR_PULSE_MS, performance.now());
    this.snapshot.patch({ notice: message });
    this.refresh();
  }
}
