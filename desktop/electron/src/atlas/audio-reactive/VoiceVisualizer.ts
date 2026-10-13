// Convierte características de audio crudas en la influencia suavizada que
// recibe el núcleo. Módulo puro.

import { EnvelopeFollower, VoiceActivityDetector, type RawAudioFeatures } from "./audioFeatures.ts";

export type VoiceLevels = { level: number; bass: number; mid: number; treble: number; voiceActive: boolean };

// La voz hablada ronda un RMS de 0.05–0.25: esta ganancia la lleva a 0..1.
const RMS_GAIN = 4.5;
const BAND_GAIN = 1.6;

const clamp01 = (value: number) => Math.max(0, Math.min(1, value));

export class VoiceVisualizer {
  private readonly level = new EnvelopeFollower(30, 5);
  private readonly bass = new EnvelopeFollower(24, 6);
  private readonly mid = new EnvelopeFollower(24, 7);
  private readonly treble = new EnvelopeFollower(28, 9);
  private readonly vad = new VoiceActivityDetector();

  /** `raw` null = no hay señal analizable: los niveles decaen a cero en vez de
      inventarse un movimiento. */
  update(raw: RawAudioFeatures | null, dt: number, now: number): VoiceLevels {
    const level = this.level.update(raw ? clamp01(raw.rms * RMS_GAIN) : 0, dt);
    const bass = this.bass.update(raw ? clamp01(raw.bass * BAND_GAIN) : 0, dt);
    const mid = this.mid.update(raw ? clamp01(raw.mid * BAND_GAIN) : 0, dt);
    const treble = this.treble.update(raw ? clamp01(raw.treble * BAND_GAIN) : 0, dt);
    const voiceActive = raw ? this.vad.update(raw.rms, now) : this.vad.update(0, now);
    return { level, bass, mid, treble, voiceActive };
  }

  reset(): void {
    this.level.reset();
    this.bass.reset();
    this.mid.reset();
    this.treble.reset();
    this.vad.reset();
  }
}
