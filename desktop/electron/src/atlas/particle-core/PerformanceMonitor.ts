// Detecta degradación sostenida del rendimiento. Módulo puro.

export type PerformanceOptions = {
  /** Por debajo de estos FPS se considera degradado. */
  minFps: number;
  /** Tiempo continuo por debajo del umbral antes de avisar. */
  sustainMs: number;
  /** Pausa tras un aviso, para dar tiempo a que el cambio de calidad surta efecto. */
  cooldownMs: number;
};

export const DEFAULT_PERFORMANCE_OPTIONS: PerformanceOptions = { minFps: 42, sustainMs: 4000, cooldownMs: 8000 };

export class PerformanceMonitor {
  private readonly options: PerformanceOptions;
  private smoothedFps = 60;
  private belowSince: number | null = null;
  private quietUntil = 0;

  constructor(options: PerformanceOptions = DEFAULT_PERFORMANCE_OPTIONS) {
    this.options = options;
  }

  get fps(): number {
    return this.smoothedFps;
  }

  /** Olvida el historial; se llama al cambiar de calidad o al reanudar el render. */
  reset(now: number): void {
    this.smoothedFps = 60;
    this.belowSince = null;
    this.quietUntil = now + this.options.cooldownMs;
  }

  /** Devuelve true una sola vez cuando la degradación se confirma. */
  sample(frameMs: number, now: number): boolean {
    // Un fotograma de más de 250 ms es una pestaña oculta o un salto del
    // sistema, no un problema de GPU: no cuenta.
    if (frameMs <= 0 || frameMs > 250) {
      this.belowSince = null;
      return false;
    }
    this.smoothedFps += (1000 / frameMs - this.smoothedFps) * 0.08;

    if (now < this.quietUntil || this.smoothedFps >= this.options.minFps) {
      this.belowSince = null;
      return false;
    }
    if (this.belowSince === null) {
      this.belowSince = now;
      return false;
    }
    if (now - this.belowSince < this.options.sustainMs) return false;

    this.belowSince = null;
    this.quietUntil = now + this.options.cooldownMs;
    return true;
  }
}
