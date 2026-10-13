// Transformaciones de audio → características. Módulo puro (sin Web Audio).

export type RawAudioFeatures = { rms: number; bass: number; mid: number; treble: number };

/** RMS de una ventana en el dominio del tiempo (bytes centrados en 128). 0..1. */
export function rmsFromTimeDomain(samples: Uint8Array): number {
  if (samples.length === 0) return 0;
  let sum = 0;
  for (let i = 0; i < samples.length; i += 1) {
    const value = (samples[i] - 128) / 128;
    sum += value * value;
  }
  return Math.sqrt(sum / samples.length);
}

export const BANDS = { bass: [20, 250], mid: [250, 2000], treble: [2000, 8000] } as const;

function bandAverage(bins: Uint8Array, hzPerBin: number, lowHz: number, highHz: number): number {
  const first = Math.max(1, Math.floor(lowHz / hzPerBin));
  const last = Math.min(bins.length - 1, Math.ceil(highHz / hzPerBin));
  if (last < first) return 0;
  let sum = 0;
  for (let i = first; i <= last; i += 1) sum += bins[i];
  return sum / ((last - first + 1) * 255);
}

/** Energía media por banda a partir del espectro de un AnalyserNode. 0..1. */
export function bandLevels(bins: Uint8Array, sampleRate: number): { bass: number; mid: number; treble: number } {
  // frequencyBinCount = fftSize / 2, así que cada bin cubre sampleRate / fftSize.
  const hzPerBin = sampleRate / (bins.length * 2);
  return {
    bass: bandAverage(bins, hzPerBin, BANDS.bass[0], BANDS.bass[1]),
    mid: bandAverage(bins, hzPerBin, BANDS.mid[0], BANDS.mid[1]),
    treble: bandAverage(bins, hzPerBin, BANDS.treble[0], BANDS.treble[1]),
  };
}

/** Seguidor de envolvente: sube rápido (ataque) y baja despacio (relajación),
    lo que evita movimientos bruscos sin perder los golpes de voz. */
export class EnvelopeFollower {
  private readonly attack: number;
  private readonly release: number;
  private current = 0;

  /** @param attack, release constantes en 1/s; mayor = más rápido. */
  constructor(attack = 30, release = 6) {
    this.attack = attack;
    this.release = release;
  }

  get value(): number {
    return this.current;
  }

  update(input: number, dt: number): number {
    const rate = input > this.current ? this.attack : this.release;
    this.current += (input - this.current) * (1 - Math.exp(-rate * dt));
    return this.current;
  }

  reset(): void {
    this.current = 0;
  }
}

export type VadOptions = { enter: number; exit: number; hangoverMs: number };

export const DEFAULT_VAD_OPTIONS: VadOptions = { enter: 0.035, exit: 0.02, hangoverMs: 350 };

/** Detector de actividad de voz por energía, con histéresis y cola de espera
    para no cortarse en las pausas entre sílabas. */
export class VoiceActivityDetector {
  private readonly options: VadOptions;
  private speaking = false;
  private lastAbove = -Infinity;

  constructor(options: VadOptions = DEFAULT_VAD_OPTIONS) {
    this.options = options;
  }

  get active(): boolean {
    return this.speaking;
  }

  update(rms: number, now: number): boolean {
    if (rms >= (this.speaking ? this.options.exit : this.options.enter)) {
      this.speaking = true;
      this.lastAbove = now;
    } else if (this.speaking && now - this.lastAbove > this.options.hangoverMs) {
      this.speaking = false;
    }
    return this.speaking;
  }

  reset(): void {
    this.speaking = false;
    this.lastAbove = -Infinity;
  }
}
