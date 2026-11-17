// Detector de voz neuronal (Silero VAD v6, ONNX, 1,2 MB) en streaming.
//
// Distingue voz de ruido por cómo suena, no por el volumen: ventiladores,
// zumbidos, teclado, golpes, lluvia o música no cuentan como voz aunque sean
// fuertes, y la voz se sigue detectando con ese ruido encima. Medido sobre un
// corpus de 30 s por sonido: 0 frases falsas en todos los ruidos y 6/6 frases
// de voz también con ventilador o música (el detector por volumen daba hasta 11
// falsas y solo 1/6 con música). ~0,2 ms por bloque de 32 ms.
//
// Corre localmente con onnxruntime-web (WASM, un hilo). El modelo es el que
// incluye faster-whisper (licencia MIT, snakers4/silero-vad).

import * as ort from "onnxruntime-web/wasm";

/** Muestras por bloque a 16 kHz (32 ms), las que espera el modelo. */
export const VAD_CHUNK = 512;
const CONTEXT = 64;
const STATE = 128;

export class SileroVad {
  private readonly session: ort.InferenceSession;
  private h = new Float32Array(STATE);
  private c = new Float32Array(STATE);
  private context = new Float32Array(CONTEXT);

  private constructor(session: ort.InferenceSession) {
    this.session = session;
  }

  /** `model`: URL o bytes del .onnx. `wasmBase`: carpeta con el runtime WASM
      (en el navegador; en Node se usa el del paquete). */
  static async create(model: string | Uint8Array, wasmBase?: string): Promise<SileroVad> {
    if (wasmBase) ort.env.wasm.wasmPaths = wasmBase;
    // Un hilo: los hilos WASM exigen aislamiento entre orígenes y Silero no los necesita.
    ort.env.wasm.numThreads = 1;
    const session = typeof model === "string" ? await ort.InferenceSession.create(model) : await ort.InferenceSession.create(model);
    return new SileroVad(session);
  }

  /** Probabilidad de voz (0..1) de un bloque de VAD_CHUNK muestras. */
  async process(chunk: Float32Array): Promise<number> {
    if (chunk.length !== VAD_CHUNK) throw new Error(`Silero espera bloques de ${VAD_CHUNK} muestras.`);
    const input = new Float32Array(CONTEXT + VAD_CHUNK);
    input.set(this.context, 0);
    input.set(chunk, CONTEXT);
    const out = await this.session.run({
      input: new ort.Tensor("float32", input, [1, CONTEXT + VAD_CHUNK]),
      h: new ort.Tensor("float32", this.h, [1, 1, STATE]),
      c: new ort.Tensor("float32", this.c, [1, 1, STATE]),
    });
    this.h = Float32Array.from(out.hn.data as Float32Array);
    this.c = Float32Array.from(out.cn.data as Float32Array);
    this.context = chunk.slice(VAD_CHUNK - CONTEXT);
    return (out.speech_probs.data as Float32Array)[0];
  }

  reset(): void {
    this.h = new Float32Array(STATE);
    this.c = new Float32Array(STATE);
    this.context = new Float32Array(CONTEXT);
  }
}

/** Adapta las tramas del micrófono (20 ms) a los bloques de Silero (32 ms) y
    mantiene la última probabilidad. La inferencia es asíncrona y en orden: el
    detector de frases usa la probabilidad más reciente (≤ ~40 ms de retraso). */
export class StreamingVad {
  private readonly vad: SileroVad;
  private buffer = new Float32Array(0);
  private queue: Float32Array[] = [];
  private running = false;
  private generation = 0;
  private latest = 0;

  constructor(vad: SileroVad) {
    this.vad = vad;
  }

  get probability(): number {
    return this.latest;
  }

  push(frame: Float32Array): void {
    const merged = new Float32Array(this.buffer.length + frame.length);
    merged.set(this.buffer, 0);
    merged.set(frame, this.buffer.length);
    let offset = 0;
    while (merged.length - offset >= VAD_CHUNK) {
      this.queue.push(merged.slice(offset, offset + VAD_CHUNK));
      offset += VAD_CHUNK;
    }
    this.buffer = merged.slice(offset);
    // Si la inferencia se atrasa (pestaña en segundo plano), no acumular
    // retraso: quedarse con lo más reciente.
    if (this.queue.length > 8) this.queue.splice(0, this.queue.length - 8);
    if (!this.running) void this.drain();
  }

  /** Espera a que se procese lo pendiente (pruebas). */
  async flush(): Promise<void> {
    while (this.running || this.queue.length) await new Promise((resolve) => setTimeout(resolve, 1));
  }

  reset(): void {
    this.generation += 1;
    this.queue = [];
    this.buffer = new Float32Array(0);
    this.latest = 0;
    this.vad.reset();
  }

  private async drain(): Promise<void> {
    this.running = true;
    const generation = this.generation;
    try {
      while (this.queue.length && generation === this.generation) {
        const probability = await this.vad.process(this.queue.shift() as Float32Array);
        if (generation === this.generation) this.latest = probability;
      }
    } catch (error) {
      console.warn("[vad] Fallo la inferencia de Silero:", error);
    } finally {
      this.running = false;
    }
  }
}
