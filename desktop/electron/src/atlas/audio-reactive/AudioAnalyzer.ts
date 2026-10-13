// Único punto de análisis de audio de la aplicación (Web Audio API). Analiza el
// micrófono mientras se graba y la voz de ATLAS mientras suena; nunca los dos a
// la vez ni dos veces el mismo flujo.

import { bandLevels, rmsFromTimeDomain, type RawAudioFeatures } from "./audioFeatures.ts";

const FFT_SIZE = 1024;

type Tap = { analyser: AnalyserNode; time: Uint8Array<ArrayBuffer>; frequency: Uint8Array<ArrayBuffer> };

export class AudioAnalyzer {
  private context: AudioContext | null = null;
  private micTap: Tap | null = null;
  private micSource: MediaStreamAudioSourceNode | null = null;
  private playbackTap: Tap | null = null;
  private playbackSource: AudioBufferSourceNode | null = null;
  private finishPlayback: (() => void) | null = null;

  get playing(): boolean {
    return this.playbackSource !== null;
  }

  /** Analiza un flujo de micrófono ya abierto por quien graba: no abre otra
      captura. No se conecta a la salida (no queremos oírnos). */
  attachMicrophone(stream: MediaStream): void {
    this.detachMicrophone();
    const context = this.ensureContext();
    this.micTap = this.createTap(context);
    this.micSource = context.createMediaStreamSource(stream);
    this.micSource.connect(this.micTap.analyser);
  }

  detachMicrophone(): void {
    this.micSource?.disconnect();
    this.micSource = null;
    this.micTap = null;
  }

  /** Reproduce audio codificado (WAV del backend) pasando por el analizador.
      La promesa se resuelve al terminar o al detenerlo. */
  async play(encoded: ArrayBuffer): Promise<void> {
    this.stopPlayback();
    const context = this.ensureContext();
    if (context.state === "suspended") await context.resume();
    const buffer = await context.decodeAudioData(encoded);
    const tap = this.createTap(context);
    const source = context.createBufferSource();
    source.buffer = buffer;
    source.connect(tap.analyser);
    tap.analyser.connect(context.destination);
    this.playbackTap = tap;
    this.playbackSource = source;
    await new Promise<void>((resolve) => {
      const finish = () => {
        if (this.playbackSource !== source) return resolve();
        source.onended = null;
        source.disconnect();
        tap.analyser.disconnect();
        this.playbackSource = null;
        this.playbackTap = null;
        this.finishPlayback = null;
        resolve();
      };
      this.finishPlayback = finish;
      source.onended = finish;
      source.start();
    });
  }

  stopPlayback(): void {
    const source = this.playbackSource;
    if (!source) return;
    try {
      source.stop();
    } catch {
      /* ya había terminado */
    }
    this.finishPlayback?.();
  }

  /** Características del audio activo, o null si no hay señal que analizar.
      La voz de ATLAS tiene prioridad sobre el micrófono. */
  sample(): RawAudioFeatures | null {
    const tap = this.playbackTap ?? this.micTap;
    if (!tap || !this.context) return null;
    tap.analyser.getByteTimeDomainData(tap.time);
    tap.analyser.getByteFrequencyData(tap.frequency);
    return { rms: rmsFromTimeDomain(tap.time), ...bandLevels(tap.frequency, this.context.sampleRate) };
  }

  dispose(): void {
    this.stopPlayback();
    this.detachMicrophone();
    void this.context?.close().catch(() => undefined);
    this.context = null;
  }

  private ensureContext(): AudioContext {
    this.context ??= new AudioContext();
    return this.context;
  }

  private createTap(context: AudioContext): Tap {
    const analyser = context.createAnalyser();
    analyser.fftSize = FFT_SIZE;
    analyser.smoothingTimeConstant = 0.55;
    return { analyser, time: new Uint8Array(analyser.fftSize), frequency: new Uint8Array(analyser.frequencyBinCount) };
  }
}
