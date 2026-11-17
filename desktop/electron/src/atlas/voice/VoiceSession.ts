// Flujo de voz del cliente Electron: escuchar → transcribir → (chat) → hablar.
//
// La escucha la decide ListeningEngine (lógica pura); aquí se conecta con el
// micrófono, el backend (por el puente IPC) y la reproducción. Hay dos formas
// de hablarle a ATLAS:
// - el botón del micrófono: escucha un comando y corta solo al callarse;
// - manos libres: el micrófono queda abierto esperando "Atlas". Se activa por
//   decisión explícita del usuario y siempre se ve en la interfaz.

import type { AudioAnalyzer } from "../audio-reactive/AudioAnalyzer.ts";
import { ListeningEngine, type EngineState, type Transcription } from "./ListeningEngine.ts";
import { MicrophoneCapture, microphoneErrorMessage } from "./MicrophoneCapture.ts";
import { encodeWav } from "./pcm.ts";
import { probabilityForSensitivity, SpeechSegmenter } from "./SpeechSegmenter.ts";
import { SileroVad, StreamingVad } from "./SileroVad.ts";
import { WAKE_PROMPT } from "./wakeWord.ts";

/** standby: manos libres, esperando "Atlas". recording: captando un comando. */
export type VoicePhase = "idle" | "standby" | "recording" | "transcribing" | "synthesizing" | "speaking";

export type VoiceTransport = (channel: string, input?: unknown) => Promise<unknown>;

export type VoiceSessionOptions = {
  analyzer: AudioAnalyzer;
  transport: VoiceTransport;
  /** Recursos del detector de voz neuronal (modelo .onnx y carpeta del runtime
      WASM). Sin ellos, o si fallan, se detecta la voz por volumen. */
  vad?: { modelUrl: string; wasmBase: string };
  onPhase: (phase: VoicePhase) => void;
  /** Texto de la frase en curso mientras se habla ("" al terminar). */
  onPartial: (text: string) => void;
  onTranscript: (text: string) => void;
  onWake: () => void;
  onError: (message: string) => void;
  /** "Solo mi voz": se ignoró una frase de otra voz. */
  onSpeakerRejected: (score: number | null) => void;
};

export type ListeningPreferences = {
  /** 0 estricta … 1 capta voz baja. */
  sensitivity: number;
  /** Tras leer una respuesta, escuchar unos segundos sin necesidad de "Atlas". */
  followUp: boolean;
  wakeSound: boolean;
  /** Umbral de parecido con la voz registrada, o null si cualquiera puede hablarle. */
  speakerThreshold: number | null;
};

/** Cola de eco de la sala tras hablar ATLAS. */
const ECHO_TAIL_MS = 250;

export class VoiceSession {
  private readonly options: VoiceSessionOptions;
  private readonly engine: ListeningEngine;
  private readonly capture: MicrophoneCapture;
  private preferences: ListeningPreferences = { sensitivity: 0.5, followUp: true, wakeSound: true, speakerThreshold: null };
  /** Mientras se graba una muestra para registrar la voz, las tramas van aquí y no al motor. */
  private sampleSink: ((frame: Float32Array) => void) | null = null;
  private cancelSampleCapture: (() => void) | null = null;
  private lastScore: number | null = null;
  private vad: StreamingVad | null = null;
  private handsFreeOn = false;
  private busy = false;
  private speech: "idle" | "synthesizing" | "speaking" = "idle";
  private speechToken = 0;
  private phase: VoicePhase = "idle";
  private partial = "";
  private analyzing = false;

  constructor(options: VoiceSessionOptions) {
    this.options = options;
    this.engine = new ListeningEngine((audio, { fast, speaker }) => this.transcribe(audio, fast, speaker), {
      onState: (state) => this.handleEngineState(state),
      onWake: () => {
        if (this.preferences.wakeSound) this.capture.chime();
        this.options.onWake();
      },
      onCommand: (text) => this.options.onTranscript(text),
      onNothingHeard: () => this.options.onError("No se entendio ninguna palabra."),
      onError: (message) => this.options.onError(message),
      onSpeakerRejected: (score) => this.options.onSpeakerRejected(score),
    });
    this.capture = new MicrophoneCapture({
      frameSize: this.engine.frameSize,
      onFrame: (frame) => {
        if (this.sampleSink) this.sampleSink(frame);
        else {
          // No dejar que la voz de ATLAS ni su eco entren al estado recurrente
          // de Silero. El motor recibe igualmente la trama para descontar la
          // cola antieco y volver a estar listo de forma determinista.
          if (this.engine.acceptsVadAudio) this.vad?.push(frame);
          this.engine.pushFrame(frame, this.vad?.probability);
        }
      },
      onEnded: () => {
        this.handsFreeOn = false;
        this.engine.stop();
        this.options.onError("El microfono se desconecto.");
      },
    });
    if (options.vad) void this.loadVad(options.vad);
  }

  /** Carga el detector neuronal; hasta entonces (o si falla) se usa el volumen. */
  private async loadVad(resources: { modelUrl: string; wasmBase: string }): Promise<void> {
    try {
      this.vad = new StreamingVad(await SileroVad.create(resources.modelUrl, resources.wasmBase));
    } catch (error) {
      console.warn("[vad] No se pudo cargar Silero; se detecta la voz por volumen:", error);
    }
  }

  /** true si la voz se detecta con el modelo neuronal (no por volumen). */
  get neuralVad(): boolean {
    return this.vad !== null;
  }

  get currentPhase(): VoicePhase {
    return this.phase;
  }

  get recording(): boolean {
    return this.phase === "recording";
  }

  get handsFree(): boolean {
    return this.handsFreeOn;
  }

  /** Nivel del micrófono, ruido de fondo (dBFS) y probabilidad de voz, para diagnóstico. */
  get levels(): { level: number; noiseFloor: number; speechProbability: number | null } | null {
    return this.capture.open ? { ...this.engine.levels, speechProbability: this.vad?.probability ?? null } : null;
  }

  /** Parecido de la última frase comparada con la voz registrada (diagnóstico). */
  get lastSpeakerScore(): number | null {
    return this.lastScore;
  }

  setPreferences(preferences: ListeningPreferences): void {
    this.preferences = preferences;
    this.engine.setSensitivity(preferences.sensitivity);
    this.engine.setSpeakerGate(preferences.speakerThreshold);
  }

  /** Graba una frase para registrar la voz: espera a que se hable y corta al
      callarse. La escucha normal queda en pausa mientras tanto. */
  async recordSample(): Promise<Float32Array> {
    this.cancelSample();
    if (!(await this.openMicrophone())) throw new Error("No se pudo abrir el microfono.");
    const segmenter = new SpeechSegmenter({ endSilenceMs: 900, maxUtteranceMs: 10000 });
    return new Promise<Float32Array>((resolve, reject) => {
      let waitedMs = 0;
      const finish = () => {
        this.sampleSink = null;
        this.cancelSampleCapture = null;
        this.syncMicrophone();
      };
      this.cancelSampleCapture = () => {
        finish();
        reject(new Error("Grabacion cancelada."));
      };
      const probabilities = probabilityForSensitivity(this.preferences.sensitivity);
      segmenter.setOptions(probabilities);
      this.sampleSink = (frame) => {
        const event = segmenter.push(frame, this.vad?.probability);
        waitedMs += 20;
        if (event === "end") {
          const audio = segmenter.audio();
          const voicedMs = segmenter.voicedMs;
          finish();
          if (voicedMs < 1000) reject(new Error("La frase fue muy corta. Leela completa."));
          else resolve(audio);
        } else if (!segmenter.active && waitedMs > 10000) {
          finish();
          reject(new Error("No se oyo ninguna frase."));
        }
      };
    });
  }

  cancelSample(): void {
    this.cancelSampleCapture?.();
  }

  /** Activa la escucha continua de "Atlas". Devuelve false si no hay micrófono. */
  async enableHandsFree(): Promise<boolean> {
    if (!(await this.openMicrophone())) return false;
    this.handsFreeOn = true;
    this.engine.startStandby();
    if (this.busy || this.speech !== "idle") this.engine.pause();
    return true;
  }

  disableHandsFree(): void {
    this.handsFreeOn = false;
    this.engine.stopStandby();
    this.syncMicrophone();
  }

  /** Botón del micrófono: escuchar un comando ya (sin decir "Atlas"). */
  async startRecording(): Promise<void> {
    if (this.phase === "recording" || this.phase === "transcribing") return;
    this.stopSpeaking();
    if (!(await this.openMicrophone())) return;
    this.engine.startCommand("manual");
  }

  /** Terminar ya la frase y enviarla. */
  stopRecording(): void {
    this.engine.finishNow();
  }

  /** Dejar de escuchar el comando sin enviar nada. */
  cancelRecording(): void {
    this.engine.cancel();
    this.syncMicrophone();
  }

  /** ATLAS está procesando una petición: no escuchar mientras tanto. */
  setBusy(busy: boolean): void {
    if (busy === this.busy) return;
    this.busy = busy;
    if (busy) this.engine.pause();
    else if (this.speech === "idle") {
      // La pausa puede haber durado varios segundos; no reutilizar el estado
      // recurrente asociado a una voz o un ruido anterior.
      this.vad?.reset();
      this.engine.resume();
    }
  }

  /** Sintetiza y reproduce `text` con la voz del backend. No lanza: un fallo de
      voz no debe afectar a la respuesta de texto, que ya está en pantalla. */
  async speak(text: string): Promise<void> {
    const clean = text.trim();
    if (!clean || this.phase === "recording") return;
    const token = ++this.speechToken;
    this.options.analyzer.stopPlayback();
    // No escucharse a sí mismo por los altavoces.
    this.engine.pause();
    this.setSpeech("synthesizing");
    let completed = false;
    try {
      const audio = await this.options.transport("atlas:speak", { text: clean });
      if (token !== this.speechToken) return;
      const bytes = audio instanceof Uint8Array ? audio : new Uint8Array(audio as ArrayBuffer);
      if (!bytes.byteLength) throw new Error("El backend no devolvio audio.");
      this.setSpeech("speaking");
      // decodeAudioData se queda con el buffer: se le pasa una copia exacta.
      await this.options.analyzer.play(bytes.buffer.slice(bytes.byteOffset, bytes.byteOffset + bytes.byteLength) as ArrayBuffer);
      completed = token === this.speechToken;
    } catch (error) {
      if (token === this.speechToken) this.options.onError(`No se pudo reproducir la voz de ATLAS: ${error instanceof Error ? error.message : String(error)}`);
    } finally {
      if (token === this.speechToken) this.afterSpeech(completed);
    }
  }

  stopSpeaking(): void {
    if (this.speech === "idle") return;
    this.speechToken += 1;
    this.options.analyzer.stopPlayback();
    this.afterSpeech(false);
  }

  dispose(): void {
    this.cancelSample();
    this.speechToken += 1;
    this.options.analyzer.stopPlayback();
    this.engine.stop();
    this.capture.stop();
    this.detachAnalyzer();
  }

  // ---------- Interno ----------

  private async openMicrophone(): Promise<boolean> {
    try {
      const wasOpen = this.capture.open;
      await this.capture.start();
      // Micrófono recién abierto: el estado del detector no sirve para otro flujo.
      if (!wasOpen) this.vad?.reset();
      return true;
    } catch (error) {
      this.options.onError(microphoneErrorMessage(error));
      return false;
    }
  }

  private async transcribe(audio: Float32Array, fast: boolean, speaker: boolean): Promise<Transcription> {
    const result = (await this.options.transport("atlas:transcribe", { audio: encodeWav(audio), mimeType: "audio/wav", fast, prompt: WAKE_PROMPT, speaker, speakerMin: speaker ? this.preferences.speakerThreshold : null })) as { text?: string; speakerScore?: number | null };
    const speakerScore = typeof result.speakerScore === "number" ? result.speakerScore : null;
    if (speakerScore !== null) this.lastScore = speakerScore;
    return { text: result.text ?? "", speakerScore };
  }

  private afterSpeech(completed: boolean): void {
    this.setSpeech("idle");
    if (this.busy) return;
    // La respuesta y su eco no deben influir en la primera decisión de VAD
    // cuando el usuario vuelve a hablar.
    this.vad?.reset();
    this.engine.resume(ECHO_TAIL_MS);
    // Conversación: tras una respuesta hablada, la siguiente pregunta no
    // necesita "Atlas" (solo en manos libres y durante unos segundos).
    if (completed && this.handsFreeOn && this.preferences.followUp) this.engine.startCommand("follow-up");
  }

  private setSpeech(speech: "idle" | "synthesizing" | "speaking"): void {
    this.speech = speech;
    this.updatePhase();
  }

  private handleEngineState(state: EngineState): void {
    if (state.partial !== this.partial) {
      this.partial = state.partial;
      this.options.onPartial(state.partial);
    }
    this.syncMicrophone();
    this.updatePhase();
  }

  /** Cierra el micrófono cuando el motor ya no lo necesita (fuera de manos libres). */
  private syncMicrophone(): void {
    if (this.engine.current.mode === "off" && !this.handsFreeOn && !this.sampleSink && this.capture.open) this.capture.stop();
  }

  private updatePhase(): void {
    const engine = this.engine.current;
    const phase: VoicePhase =
      this.speech !== "idle" ? this.speech
      : engine.finalizing ? "transcribing"
      : engine.capturing ? "recording"
      : engine.mode === "standby" || (engine.mode === "paused" && this.handsFreeOn) ? "standby"
      : "idle";
    // El núcleo reacciona a la voz del usuario solo cuando le habla a ATLAS,
    // no al ruido de la sala mientras espera "Atlas".
    if (phase === "recording") this.attachAnalyzer();
    else this.detachAnalyzer();
    if (phase === this.phase) return;
    this.phase = phase;
    this.options.onPhase(phase);
  }

  private attachAnalyzer(): void {
    const stream = this.capture.mediaStream;
    if (this.analyzing || !stream) return;
    this.analyzing = true;
    this.options.analyzer.attachMicrophone(stream);
  }

  private detachAnalyzer(): void {
    if (!this.analyzing) return;
    this.analyzing = false;
    this.options.analyzer.detachMicrophone();
  }
}
