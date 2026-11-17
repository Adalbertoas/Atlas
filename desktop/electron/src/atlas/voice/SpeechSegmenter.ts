// Detecta dónde empieza y termina cada frase en un flujo continuo de micrófono.
// Módulo puro: recibe tramas PCM y devuelve eventos; el tiempo sale de las
// propias tramas, así que es determinista en las pruebas.
//
// Qué trama es voz lo decide, si se le pasa, la probabilidad del detector
// neuronal (SileroVad): así el ruido de fondo no cuenta aunque sea fuerte. Sin
// ella (modelo no disponible, pruebas) se usa el volumen sobre el ruido de fondo
// medido (percentil bajo de los últimos segundos); un umbral fijo fallaba en
// cuanto cambiaba el micrófono o el ambiente (ver desktop/atlas_desktop/wake_word.py).

import { frameDb } from "./pcm.ts";

export type SegmenterOptions = {
  sampleRate: number;
  frameMs: number;
  /** Audio previo al inicio detectado que se conserva: no cortar la primera sílaba. */
  preRollMs: number;
  /** Voz continua necesaria para dar por empezada una frase (descarta clics). */
  minSpeechMs: number;
  /** Silencio que da por terminada la frase. */
  endSilenceMs: number;
  /** Silencio a partir del cual se avisa de una pausa (transcripción anticipada). */
  pauseMs: number;
  maxUtteranceMs: number;
  /** dB por encima del ruido de fondo para considerar que hay voz. */
  marginDb: number;
  /** Nivel mínimo absoluto: por debajo nunca es voz, aunque el fondo sea muy silencioso. */
  minLevelDb: number;
  /** Ventana sobre la que se estima el ruido de fondo. */
  noiseWindowMs: number;
  /** Ruido de fondo supuesto al abrir el micrófono, antes de medir nada. */
  initialNoiseDb: number;
  /** El fondo baja al instante pero sube despacio: si alguien empieza a hablar
      justo al abrir el micrófono, su voz no debe convertirse en "el fondo". */
  noiseRiseDbPerSecond: number;
  /** Con detector neuronal: probabilidad para empezar a contar voz y para seguir
      contándola (histéresis: no cortar en sílabas débiles). */
  enterProbability: number;
  exitProbability: number;
  /** Con detector neuronal: nivel mínimo absoluto (más bajo que minLevelDb: el
      detector ya descarta el ruido, esto solo evita susurros lejanos). */
  vadMinLevelDb: number;
};

export const DEFAULT_SEGMENTER_OPTIONS: SegmenterOptions = {
  sampleRate: 16000,
  frameMs: 20,
  preRollMs: 300,
  minSpeechMs: 120,
  endSilenceMs: 700,
  pauseMs: 300,
  maxUtteranceMs: 15000,
  marginDb: 12,
  minLevelDb: -50,
  noiseWindowMs: 3000,
  initialNoiseDb: -65,
  noiseRiseDbPerSecond: 6,
  enterProbability: 0.5,
  exitProbability: 0.35,
  vadMinLevelDb: -60,
};

/** Sensibilidad 0 (estricta) … 1 (capta voz baja) → margen sobre el ruido. */
export function marginForSensitivity(sensitivity: number): number {
  const s = Math.max(0, Math.min(1, sensitivity));
  return 18 - s * 12;
}

/** Sensibilidad 0 (estricta) … 1 (capta voz baja) → probabilidad de voz exigida. */
export function probabilityForSensitivity(sensitivity: number): { enterProbability: number; exitProbability: number } {
  const s = Math.max(0, Math.min(1, sensitivity));
  const enterProbability = Math.round((0.7 - s * 0.4) * 100) / 100;
  return { enterProbability, exitProbability: Math.round((enterProbability - 0.15) * 100) / 100 };
}

export type SegmenterEvent = "start" | "pause" | "end";

const NOISE_PERCENTILE = 0.1;
const NOISE_RECOMPUTE_FRAMES = 10;

export class SpeechSegmenter {
  private options: SegmenterOptions;
  private readonly frameSamples: number;
  private readonly preRollFrames: number;
  private readonly noiseFrames: number;
  private noiseHistory: number[] = [];
  private noiseFloorDb: number;
  private framesSinceNoise = 0;
  private preRoll: Float32Array[] = [];
  private utterance: Float32Array[] = [];
  private inUtterance = false;
  private voicedRun = 0;
  private silentRun = 0;
  private pauseSignalled = false;
  private voicedFrames = 0;
  private lastVoicedFrame = 0;
  private lastDb = -100;

  constructor(options: Partial<SegmenterOptions> = {}) {
    this.options = { ...DEFAULT_SEGMENTER_OPTIONS, ...options };
    this.frameSamples = Math.round((this.options.sampleRate * this.options.frameMs) / 1000);
    this.preRollFrames = Math.ceil(this.options.preRollMs / this.options.frameMs);
    this.noiseFrames = Math.ceil(this.options.noiseWindowMs / this.options.frameMs);
    this.noiseFloorDb = this.options.initialNoiseDb;
  }

  get frameSize(): number {
    return this.frameSamples;
  }

  get active(): boolean {
    return this.inUtterance;
  }

  get noiseFloor(): number {
    return this.noiseFloorDb;
  }

  get level(): number {
    return this.lastDb;
  }

  /** Duración de la frase en curso (incluye el pre-roll). */
  get durationMs(): number {
    return this.utterance.length * this.options.frameMs;
  }

  /** Milisegundos con voz dentro de la frase en curso. */
  get voicedMs(): number {
    return this.voicedFrames * this.options.frameMs;
  }

  /** Muestras hasta el final de la última trama con voz. Una transcripción que
      cubra al menos esto ya contiene todo lo que se dijo. */
  get voicedEndSamples(): number {
    return this.lastVoicedFrame * this.frameSamples;
  }

  get sampleCount(): number {
    return this.utterance.length * this.frameSamples;
  }

  setOptions(patch: Partial<Pick<SegmenterOptions, "endSilenceMs" | "marginDb" | "maxUtteranceMs" | "enterProbability" | "exitProbability">>): void {
    this.options = { ...this.options, ...patch };
  }

  /** Copia del audio de la frase en curso. */
  audio(): Float32Array {
    const out = new Float32Array(this.sampleCount);
    this.utterance.forEach((frame, index) => out.set(frame, index * this.frameSamples));
    return out;
  }

  /** `speechProbability`: la del detector neuronal para esta trama, si lo hay. */
  push(frame: Float32Array, speechProbability?: number): SegmenterEvent | null {
    const db = frameDb(frame);
    this.lastDb = db;
    this.trackNoise(db);
    const voiced =
      speechProbability === undefined
        ? db >= Math.max(this.noiseFloorDb + this.options.marginDb, this.options.minLevelDb)
        : speechProbability >= (this.inUtterance ? this.options.exitProbability : this.options.enterProbability) && db >= this.options.vadMinLevelDb;
    const copy = Float32Array.from(frame);

    if (!this.inUtterance) {
      this.preRoll.push(copy);
      if (this.preRoll.length > this.preRollFrames) this.preRoll.shift();
      this.voicedRun = voiced ? this.voicedRun + 1 : 0;
      if (this.voicedRun * this.options.frameMs < this.options.minSpeechMs) return null;
      this.inUtterance = true;
      this.utterance = this.preRoll;
      this.preRoll = [];
      this.voicedFrames = this.voicedRun;
      this.lastVoicedFrame = this.utterance.length;
      this.silentRun = 0;
      this.pauseSignalled = false;
      return "start";
    }

    this.utterance.push(copy);
    if (voiced) {
      this.voicedFrames += 1;
      this.lastVoicedFrame = this.utterance.length;
      this.silentRun = 0;
      this.pauseSignalled = false;
    } else {
      this.silentRun += 1;
    }
    const silentMs = this.silentRun * this.options.frameMs;
    if (silentMs >= this.options.endSilenceMs || this.durationMs >= this.options.maxUtteranceMs) return "end";
    if (!this.pauseSignalled && silentMs >= this.options.pauseMs) {
      this.pauseSignalled = true;
      return "pause";
    }
    return null;
  }

  /** Cierra la frase en curso (tras "end") y vuelve a esperar voz. Conserva la
      estimación de ruido. */
  finishUtterance(): void {
    this.inUtterance = false;
    this.utterance = [];
    this.preRoll = [];
    this.voicedRun = 0;
    this.silentRun = 0;
    this.voicedFrames = 0;
    this.lastVoicedFrame = 0;
  }

  /** Olvida también el ruido de fondo (otro micrófono, otra sesión). */
  reset(): void {
    this.finishUtterance();
    this.noiseHistory = [];
    this.noiseFloorDb = this.options.initialNoiseDb;
    this.framesSinceNoise = 0;
  }

  private trackNoise(db: number): void {
    this.noiseHistory.push(db);
    if (this.noiseHistory.length > this.noiseFrames) this.noiseHistory.shift();
    this.framesSinceNoise += 1;
    // Recalcular cada pocas tramas: ordenar 150 valores en cada trama sería un desperdicio.
    if (this.framesSinceNoise < NOISE_RECOMPUTE_FRAMES) return;
    const elapsedS = (this.framesSinceNoise * this.options.frameMs) / 1000;
    this.framesSinceNoise = 0;
    const sorted = [...this.noiseHistory].sort((a, b) => a - b);
    const target = sorted[Math.floor((sorted.length - 1) * NOISE_PERCENTILE)];
    this.noiseFloorDb = target <= this.noiseFloorDb ? target : Math.min(target, this.noiseFloorDb + this.options.noiseRiseDbPerSecond * elapsedS);
  }
}
