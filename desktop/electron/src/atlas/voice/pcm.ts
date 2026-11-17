// Audio PCM en float32: nivel, remuestreo en flujo y codificación WAV.
// Módulo puro (sin Web Audio): lo usan la captura del micrófono y las pruebas.

/** Frecuencia que espera Whisper. Mandarle WAV PCM16 a 16 kHz evita que el
    backend tenga que decodificar webm/opus. */
export const SPEECH_SAMPLE_RATE = 16000;

/** Nivel RMS de un bloque, en dBFS (0 = escala completa). El silencio digital
    devuelve -100 en lugar de -Infinity para poder promediar. */
export function frameDb(samples: Float32Array): number {
  if (samples.length === 0) return -100;
  let sum = 0;
  for (let i = 0; i < samples.length; i += 1) sum += samples[i] * samples[i];
  const rms = Math.sqrt(sum / samples.length);
  return rms > 1e-5 ? 20 * Math.log10(rms) : -100;
}

/** Remuestreo lineal en flujo: admite bloques de cualquier tamaño y conserva la
    fase entre bloques, así no aparecen clics en las uniones. Suficiente para voz
    (el micrófono ya filtra por encima de 8 kHz en la práctica). */
export class StreamingResampler {
  private readonly step: number;
  private position = 0;
  private previous = 0;
  private primed = false;

  constructor(fromRate: number, toRate: number) {
    this.step = fromRate / toRate;
  }

  get passthrough(): boolean {
    return this.step === 1;
  }

  process(input: Float32Array): Float32Array {
    if (this.passthrough) return input;
    if (input.length === 0) return new Float32Array(0);
    // `position` es relativa al bloque actual; -1 apunta a la última muestra
    // del bloque anterior.
    if (!this.primed) {
      this.primed = true;
      this.previous = input[0];
    }
    const out: number[] = [];
    while (this.position < input.length - 1) {
      const index = Math.floor(this.position);
      const frac = this.position - index;
      const a = index < 0 ? this.previous : input[index];
      const b = input[index + 1];
      out.push(a + (b - a) * frac);
      this.position += this.step;
    }
    this.position -= input.length;
    this.previous = input[input.length - 1];
    return Float32Array.from(out);
  }

  reset(): void {
    this.position = 0;
    this.previous = 0;
    this.primed = false;
  }
}

/** Agrupa bloques de tamaño arbitrario (128 muestras del AudioWorklet) en
    tramas de tamaño fijo para el detector de voz. */
export class FrameAssembler {
  private readonly size: number;
  private buffer: Float32Array;
  private filled = 0;

  constructor(size: number) {
    this.size = size;
    this.buffer = new Float32Array(size);
  }

  push(input: Float32Array, onFrame: (frame: Float32Array) => void): void {
    let offset = 0;
    while (offset < input.length) {
      const take = Math.min(this.size - this.filled, input.length - offset);
      this.buffer.set(input.subarray(offset, offset + take), this.filled);
      this.filled += take;
      offset += take;
      if (this.filled === this.size) {
        onFrame(this.buffer);
        this.buffer = new Float32Array(this.size);
        this.filled = 0;
      }
    }
  }

  reset(): void {
    this.filled = 0;
  }
}

/** WAV PCM 16 bits mono. */
export function encodeWav(samples: Float32Array, sampleRate = SPEECH_SAMPLE_RATE): Uint8Array {
  const bytes = new Uint8Array(44 + samples.length * 2);
  const view = new DataView(bytes.buffer);
  const ascii = (offset: number, text: string) => {
    for (let i = 0; i < text.length; i += 1) bytes[offset + i] = text.charCodeAt(i);
  };
  ascii(0, "RIFF");
  view.setUint32(4, 36 + samples.length * 2, true);
  ascii(8, "WAVE");
  ascii(12, "fmt ");
  view.setUint32(16, 16, true);
  view.setUint16(20, 1, true); // PCM
  view.setUint16(22, 1, true); // mono
  view.setUint32(24, sampleRate, true);
  view.setUint32(28, sampleRate * 2, true);
  view.setUint16(32, 2, true);
  view.setUint16(34, 16, true);
  ascii(36, "data");
  view.setUint32(40, samples.length * 2, true);
  for (let i = 0; i < samples.length; i += 1) {
    const value = Math.max(-1, Math.min(1, samples[i]));
    view.setInt16(44 + i * 2, value < 0 ? value * 0x8000 : value * 0x7fff, true);
  }
  return bytes;
}
