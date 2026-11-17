// Escucha en vivo: decide qué frases transcribir, detecta "Atlas", muestra el
// texto mientras se habla y entrega el comando al terminar la frase.
//
// Lógica pura: recibe tramas PCM ya a 16 kHz y una función que transcribe. El
// reloj son las propias tramas (20 ms cada una), así que es determinista y se
// prueba sin micrófono ni backend.
//
// Cada transcripción cuesta lo mismo, ~650 ms en CPU con Whisper base, sea cual
// sea la duración del audio (medido en esta máquina). Por eso no se transcribe
// todo lo que suena:
// - en reposo, una frase solo se transcribe si tiene voz, y se abandona en
//   cuanto la primera parcial muestra que no empieza por "Atlas";
// - al detectar una pausa se transcribe por adelantado: si la frase termina
//   ahí, ese resultado ya es el final y se ahorra una transcripción entera.

import { marginForSensitivity, probabilityForSensitivity, SpeechSegmenter, type SegmenterOptions } from "./SpeechSegmenter.ts";
import { cleanTranscript, detectWakeWord, words } from "./wakeWord.ts";

export type EngineMode = "off" | "standby" | "command" | "paused";

/** Por qué se está escuchando un comando. */
export type CommandReason = "manual" | "wake" | "follow-up";

/** `speaker`: pedir también el parecido con la voz registrada ("solo mi voz"). */
export type TranscribeFn = (audio: Float32Array, options: { fast: boolean; speaker: boolean }) => Promise<Transcription>;

/** speakerScore: parecido con la voz registrada (-1..1), o null si no se pidió
    o no se pudo juzgar. */
export type Transcription = { text: string; speakerScore: number | null };

export type EngineState = {
  mode: EngineMode;
  /** Se está captando una frase dirigida a ATLAS (estado LISTENING). */
  capturing: boolean;
  /** Texto parcial de la frase en curso (sin la palabra de activación). */
  partial: string;
  /** La frase terminó y se espera la transcripción final. */
  finalizing: boolean;
};

export type EngineCallbacks = {
  onState: (state: EngineState) => void;
  onWake: () => void;
  onCommand: (text: string) => void;
  /** Se pidió un comando (botón o tras la palabra) y no llegó nada utilizable. */
  onNothingHeard: (reason: CommandReason) => void;
  onError: (message: string) => void;
  /** "Solo mi voz": una frase dirigida a ATLAS no era de la voz registrada. */
  onSpeakerRejected: (score: number | null) => void;
};

export type EngineOptions = {
  segmenter?: Partial<SegmenterOptions>;
  /** Primera parcial en reposo: lo justo para oír "Atlas" y algo más. */
  standbyFirstPartialMs: number;
  /** Primera parcial en modo comando. */
  commandFirstPartialMs: number;
  /** Separación mínima entre parciales mientras se habla. */
  partialEveryMs: number;
  /** En reposo, si tras esta voz no apareció "Atlas" al principio, se ignora la frase. */
  standbyGiveUpMs: number;
  /** Silencio de fin de frase según el modo: en reposo basta con poco ("Atlas"
      suelto); en un comando se tolera más para pensar entre palabras. */
  standbyEndSilenceMs: number;
  commandEndSilenceMs: number;
  /** Tiempo para empezar a hablar tras pedir un comando. */
  awaitMs: Record<CommandReason, number>;
  /** Frases más cortas que esto se descartan sin transcribir (golpes, clics). */
  minVoicedMs: number;
};

export const DEFAULT_ENGINE_OPTIONS: EngineOptions = {
  standbyFirstPartialMs: 1100,
  commandFirstPartialMs: 700,
  partialEveryMs: 900,
  standbyGiveUpMs: 2200,
  standbyEndSilenceMs: 550,
  commandEndSilenceMs: 800,
  awaitMs: { manual: 8000, wake: 6000, "follow-up": 5000 },
  minVoicedMs: 200,
};

type Utterance = {
  id: number;
  /** unknown: en reposo, aún no se sabe si empieza por "Atlas". */
  decision: "unknown" | "command" | "ignored";
  reason: CommandReason | null;
  lastRequestMs: number;
  /** Mejor resultado recibido y cuántas muestras cubría. */
  best: { text: string; coverage: number; speakerScore: number | null } | null;
  inflight: { promise: Promise<void>; coverage: number } | null;
  /** Llegó una pausa con otra transcripción en curso: lanzar la anticipada al terminar. */
  pauseQueued: boolean;
};

const FRAME_MS = 20;

export class ListeningEngine {
  private readonly transcribe: TranscribeFn;
  private readonly callbacks: EngineCallbacks;
  private readonly options: EngineOptions;
  private readonly segmenter: SpeechSegmenter;
  private mode: EngineMode = "off";
  /** Modo al que se vuelve al terminar un comando o salir de pausa. */
  private handsFree = false;
  private pendingCommand: CommandReason | null = null;
  private awaitLeftMs = 0;
  private deafMs = 0;
  private utterance: Utterance | null = null;
  private nextId = 1;
  private finalizing = 0;
  private state: EngineState = { mode: "off", capturing: false, partial: "", finalizing: false };
  /** "Solo mi voz": umbral de parecido, o null si cualquiera puede hablarle. */
  private speakerThreshold: number | null = null;

  constructor(transcribe: TranscribeFn, callbacks: EngineCallbacks, options: Partial<EngineOptions> = {}) {
    this.transcribe = transcribe;
    this.callbacks = callbacks;
    this.options = { ...DEFAULT_ENGINE_OPTIONS, ...options, awaitMs: { ...DEFAULT_ENGINE_OPTIONS.awaitMs, ...options.awaitMs } };
    this.segmenter = new SpeechSegmenter({ frameMs: FRAME_MS, ...options.segmenter });
  }

  get frameSize(): number {
    return this.segmenter.frameSize;
  }

  get current(): EngineState {
    return this.state;
  }

  /** Si el detector neuronal debe recibir audio en este instante.
      Mientras ATLAS está en pausa, o durante la breve cola antieco al volver
      a escuchar, alimentar Silero con los altavoces hace que arrastre una
      probabilidad de voz alta a la siguiente frase del usuario. El motor sí
      sigue recibiendo las tramas para que la cuenta antieco avance. */
  get acceptsVadAudio(): boolean {
    return this.mode !== "off" && this.mode !== "paused" && this.deafMs <= 0;
  }

  /** Para la interfaz de diagnóstico: nivel actual y ruido de fondo en dB. */
  get levels(): { level: number; noiseFloor: number } {
    return { level: this.segmenter.level, noiseFloor: this.segmenter.noiseFloor };
  }

  /** 0 estricta … 1 capta voz baja. Ajusta el detector neuronal y, como plan B, el de volumen. */
  setSensitivity(sensitivity: number): void {
    this.segmenter.setOptions({ marginDb: marginForSensitivity(sensitivity), ...probabilityForSensitivity(sensitivity) });
  }

  /** Solo obedecer en manos libres a la voz registrada (null = a cualquiera).
      El botón del micrófono no se filtra: pulsarlo ya es una acción del usuario. */
  setSpeakerGate(threshold: number | null): void {
    this.speakerThreshold = threshold;
  }

  /** Escucha continua esperando "Atlas". */
  startStandby(): void {
    this.handsFree = true;
    if (this.mode === "off") this.enter("standby");
  }

  /** Apaga la escucha continua. Un comando en curso se termina igualmente. */
  stopStandby(): void {
    this.handsFree = false;
    if (this.mode === "standby" || (this.mode === "paused" && !this.pendingCommand)) this.stop();
  }

  /** Escucha un comando ya, sin palabra de activación. */
  startCommand(reason: CommandReason = "manual"): void {
    if (reason === "follow-up" && !this.handsFree) return;
    this.discardUtterance();
    this.pendingCommand = reason;
    this.awaitLeftMs = this.options.awaitMs[reason];
    this.enter("command");
  }

  /** Termina ya la frase en curso (botón "detener y enviar"). */
  finishNow(): void {
    if (this.utterance && this.utterance.decision !== "ignored") {
      void this.finalize();
      return;
    }
    if (this.mode === "command") this.endCommand(this.pendingCommand ?? "manual", false);
  }

  /** Deja de escuchar sin enviar nada. */
  cancel(): void {
    this.discardUtterance();
    this.pendingCommand = null;
    this.enter(this.handsFree ? "standby" : "off");
  }

  /** ATLAS está pensando o hablando: no escuchar (evita oírse a sí mismo). */
  pause(): void {
    if (this.mode === "off") return;
    this.discardUtterance();
    this.pendingCommand = null;
    this.enter("paused");
  }

  /** Vuelve a escuchar tras una pausa. `deafMs` ignora la cola de eco de la sala. */
  resume(deafMs = 0): void {
    if (this.mode !== "paused") return;
    this.deafMs = deafMs;
    this.enter(this.handsFree ? "standby" : "off");
  }

  stop(): void {
    this.handsFree = false;
    this.discardUtterance();
    this.pendingCommand = null;
    this.enter("off");
    this.segmenter.reset();
  }

  /** Una trama de `frameSize` muestras a 16 kHz, con la probabilidad de voz del
      detector neuronal si está disponible. */
  pushFrame(frame: Float32Array, speechProbability?: number): void {
    if (this.mode === "off" || this.mode === "paused") return;
    if (this.deafMs > 0) {
      this.deafMs -= FRAME_MS;
      return;
    }
    const event = this.segmenter.push(frame, speechProbability);
    if (event === "start") this.beginUtterance();
    if (!this.utterance) {
      this.tickAwait();
      return;
    }
    if (event === "end") {
      void this.finalize();
      return;
    }
    const utterance = this.utterance;
    // Golpes y clics breves no merecen una transcripción.
    if (utterance.decision === "ignored" || this.segmenter.voicedMs < this.options.minVoicedMs) return;
    if (event === "pause") {
      // Anticipada: si la frase termina en esta pausa, este será el texto final.
      if (utterance.inflight) utterance.pauseQueued = true;
      else this.request(utterance, false);
      return;
    }
    if (utterance.inflight) return;
    const elapsed = this.segmenter.durationMs;
    const first = utterance.decision === "unknown" ? this.options.standbyFirstPartialMs : this.options.commandFirstPartialMs;
    if (elapsed >= first && elapsed - utterance.lastRequestMs >= this.options.partialEveryMs) this.request(utterance, true);
  }

  // ---------- Interno ----------

  private enter(mode: EngineMode): void {
    this.mode = mode;
    this.segmenter.setOptions({ endSilenceMs: mode === "command" ? this.options.commandEndSilenceMs : this.options.standbyEndSilenceMs });
    this.publish();
  }

  private publish(): void {
    const utterance = this.utterance;
    const capturing = this.mode === "command" || utterance?.decision === "command";
    const partial = utterance?.decision === "command" && !this.voiceRejected(utterance, utterance.best?.speakerScore ?? null, true) ? this.partialText(utterance) : "";
    const next: EngineState = { mode: this.mode, capturing, partial, finalizing: this.finalizing > 0 };
    const previous = this.state;
    if (previous.mode === next.mode && previous.capturing === next.capturing && previous.partial === next.partial && previous.finalizing === next.finalizing) return;
    this.state = next;
    this.callbacks.onState(next);
  }

  private partialText(utterance: Utterance): string {
    const text = utterance.best?.text ?? "";
    const wake = detectWakeWord(text);
    return wake.detected ? wake.command : text;
  }

  private needsSpeaker(utterance: Utterance): boolean {
    return this.speakerThreshold !== null && utterance.reason !== "manual";
  }

  /** ¿La voz de esta frase no es la registrada? `lenient`: una puntuación que
      aún no se pudo calcular (frase corta) no cuenta como rechazo. */
  private voiceRejected(utterance: Utterance, score: number | null, lenient = false): boolean {
    if (!this.needsSpeaker(utterance)) return false;
    if (score === null) return !lenient;
    return score < (this.speakerThreshold as number);
  }

  private tickAwait(): void {
    if (this.mode !== "command" || !this.pendingCommand) return;
    this.awaitLeftMs -= FRAME_MS;
    if (this.awaitLeftMs <= 0) this.endCommand(this.pendingCommand, true);
  }

  private beginUtterance(): void {
    const command = this.mode === "command";
    this.utterance = {
      id: this.nextId++,
      decision: command ? "command" : "unknown",
      reason: command ? this.pendingCommand : null,
      lastRequestMs: 0,
      best: null,
      inflight: null,
      pauseQueued: false,
    };
    // Ya empezó a hablar: la cuenta atrás de espera se detiene (la frase y su
    // transcripción pueden durar más que ella).
    if (command) this.pendingCommand = null;
    this.publish();
  }

  private request(utterance: Utterance, fast: boolean): void {
    const audio = this.segmenter.audio();
    const coverage = audio.length;
    utterance.lastRequestMs = this.segmenter.durationMs;
    if (!fast) utterance.pauseQueued = false;
    const promise = this.transcribe(audio, { fast, speaker: this.needsSpeaker(utterance) })
      .then((result) => this.accept(utterance, cleanTranscript(result.text), result.speakerScore, coverage))
      .catch((error: unknown) => {
        if (this.utterance === utterance) this.callbacks.onError(`No se pudo transcribir: ${error instanceof Error ? error.message : String(error)}`);
      })
      .finally(() => {
        if (utterance.inflight?.promise !== promise) return;
        utterance.inflight = null;
        if (utterance.pauseQueued && this.utterance === utterance && utterance.decision !== "ignored") {
          utterance.pauseQueued = false;
          if (this.segmenter.sampleCount > (utterance.best?.coverage ?? 0)) this.request(utterance, false);
        }
      });
    utterance.inflight = { promise, coverage };
  }

  private accept(utterance: Utterance, text: string, speakerScore: number | null, coverage: number): void {
    if (coverage >= (utterance.best?.coverage ?? 0)) utterance.best = { text, coverage, speakerScore };
    if (this.utterance !== utterance) return;
    if (utterance.decision === "unknown") {
      if (detectWakeWord(text).detected && this.voiceRejected(utterance, speakerScore, true)) {
        // Dijo "Atlas" pero no parece la voz registrada: no activarse todavía;
        // la frase completa (más audio, huella más fiable) decide al final.
      } else if (detectWakeWord(text).detected) {
        utterance.decision = "command";
        utterance.reason = "wake";
        this.segmenter.setOptions({ endSilenceMs: this.options.commandEndSilenceMs });
        this.callbacks.onWake();
      } else if (words(text).length >= 2 || this.segmenter.voicedMs >= this.options.standbyGiveUpMs) {
        // Ya hay palabras y ninguna es "Atlas" al principio: no es para ATLAS.
        utterance.decision = "ignored";
      }
    }
    this.publish();
  }

  private async finalize(): Promise<void> {
    const utterance = this.utterance;
    if (!utterance) return;
    const voicedEnd = this.segmenter.voicedEndSamples;
    const voicedMs = this.segmenter.voicedMs;
    const audio = this.segmenter.audio();
    this.segmenter.finishUtterance();
    this.utterance = null;

    if (voicedMs < this.options.minVoicedMs && utterance.decision === "command" && utterance.reason) {
      // Un golpe o un clic mientras se esperaba el comando: seguir esperando
      // con el tiempo que quedaba.
      this.pendingCommand = utterance.reason;
      this.publish();
      return;
    }
    if (utterance.decision === "ignored" || voicedMs < this.options.minVoicedMs) {
      this.afterUtterance(utterance, null);
      return;
    }

    this.finalizing += 1;
    this.publish();
    let text: string | null = null;
    let speakerScore: number | null = null;
    try {
      utterance.pauseQueued = false;
      if (utterance.inflight) await utterance.inflight.promise;
      // Reutiliza una transcripción que ya cubre toda la voz (la anticipada de
      // la pausa); si no, transcribe la frase completa.
      if (utterance.best && utterance.best.coverage >= voicedEnd) ({ text, speakerScore } = utterance.best);
      else {
        const result = await this.transcribe(audio, { fast: false, speaker: this.needsSpeaker(utterance) });
        text = cleanTranscript(result.text);
        speakerScore = result.speakerScore;
      }
    } catch (error) {
      this.callbacks.onError(`No se pudo transcribir: ${error instanceof Error ? error.message : String(error)}`);
    } finally {
      this.finalizing -= 1;
    }
    // Si mientras tanto se pausó o se apagó, el resultado ya no interesa.
    if (this.mode === "off" || this.mode === "paused") {
      this.publish();
      return;
    }
    this.afterUtterance(utterance, text, speakerScore);
  }

  private afterUtterance(utterance: Utterance, text: string | null, speakerScore: number | null = null): void {
    const wake = detectWakeWord(text ?? "");
    const directed = utterance.decision === "command" || wake.detected;
    if (text && directed) {
      const command = utterance.decision === "command" && !wake.detected ? text : wake.command;
      // Un "Atlas" suelto demasiado corto para juzgar la voz sí abre la espera:
      // el comando que siga se verifica igualmente.
      if (this.voiceRejected(utterance, speakerScore, !command.trim())) {
        this.pendingCommand = null;
        this.enter(this.handsFree ? "standby" : "off");
        this.callbacks.onSpeakerRejected(speakerScore);
        return;
      }
    }
    if (utterance.decision === "command") {
      const command = (wake.detected ? wake.command : (text ?? "")).trim();
      if (command) {
        this.submit(command);
        return;
      }
      if (wake.detected || utterance.reason === "wake") {
        // Solo dijo "Atlas": esperar el comando.
        this.startAwaiting("wake");
        return;
      }
      this.endCommand(utterance.reason ?? "manual", true);
      return;
    }
    if (utterance.decision === "unknown" && wake.detected) {
      this.callbacks.onWake();
      if (wake.command) this.submit(wake.command);
      else this.startAwaiting("wake");
      return;
    }
    // Frase de fondo: seguir como estaba (en reposo o esperando el comando).
    if (this.mode === "command" && this.pendingCommand) {
      this.publish();
      return;
    }
    this.enter(this.handsFree ? "standby" : "off");
  }

  private startAwaiting(reason: CommandReason): void {
    // Mientras se transcribía "Atlas" el usuario ya pudo empezar el comando
    // (pausa corta). Esa frase en curso es el comando, aunque en reposo se
    // hubiera tomado por conversación de fondo.
    const current = this.utterance;
    if (current) {
      current.decision = "command";
      current.reason = reason;
      this.pendingCommand = null;
      this.enter("command");
      return;
    }
    this.pendingCommand = reason;
    this.awaitLeftMs = this.options.awaitMs[reason];
    this.enter("command");
  }

  private submit(text: string): void {
    this.pendingCommand = null;
    this.enter(this.handsFree ? "standby" : "off");
    this.callbacks.onCommand(text);
  }

  private endCommand(reason: CommandReason, nothingHeard: boolean): void {
    this.pendingCommand = null;
    this.discardUtterance();
    this.enter(this.handsFree ? "standby" : "off");
    // Tras "Atlas" o una respuesta, el silencio es normal: solo se avisa si se
    // pulsó el micrófono y no se oyó nada.
    if (nothingHeard && reason === "manual") this.callbacks.onNothingHeard(reason);
  }

  private discardUtterance(): void {
    if (this.utterance) this.segmenter.finishUtterance();
    this.utterance = null;
  }
}
