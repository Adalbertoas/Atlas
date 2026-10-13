// Suavizado de landmarks con el filtro One Euro: mucho filtrado cuando la mano
// está quieta (sin temblor) y poco cuando se mueve rápido (sin retardo). Módulo puro.

import type { Landmark } from "./types.ts";

export type SmootherOptions = { minCutoff: number; beta: number; derivativeCutoff: number };

export const DEFAULT_SMOOTHER_OPTIONS: SmootherOptions = { minCutoff: 1.5, beta: 8, derivativeCutoff: 1 };

function alpha(cutoff: number, dt: number): number {
  const tau = 1 / (2 * Math.PI * cutoff);
  return 1 / (1 + tau / dt);
}

export class OneEuroFilter {
  private readonly options: SmootherOptions;
  private value: number | null = null;
  private derivative = 0;
  private lastTime = 0;

  constructor(options: SmootherOptions = DEFAULT_SMOOTHER_OPTIONS) {
    this.options = options;
  }

  filter(input: number, timeSeconds: number): number {
    if (this.value === null) {
      this.value = input;
      this.lastTime = timeSeconds;
      return input;
    }
    const dt = Math.max(timeSeconds - this.lastTime, 1e-3);
    this.lastTime = timeSeconds;
    const rawDerivative = (input - this.value) / dt;
    this.derivative += alpha(this.options.derivativeCutoff, dt) * (rawDerivative - this.derivative);
    const cutoff = this.options.minCutoff + this.options.beta * Math.abs(this.derivative);
    this.value += alpha(cutoff, dt) * (input - this.value);
    return this.value;
  }
}

const LANDMARK_COUNT = 21;

export class LandmarkSmoother {
  private readonly options: SmootherOptions;
  private readonly filters = new Map<string, OneEuroFilter[]>();

  constructor(options: SmootherOptions = DEFAULT_SMOOTHER_OPTIONS) {
    this.options = options;
  }

  /** `key` identifica la mano entre fotogramas (lateralidad o índice). */
  smooth(key: string, landmarks: readonly Landmark[], timestampMs: number): Landmark[] {
    let filters = this.filters.get(key);
    if (!filters) {
      filters = Array.from({ length: LANDMARK_COUNT * 3 }, () => new OneEuroFilter(this.options));
      this.filters.set(key, filters);
    }
    const t = timestampMs / 1000;
    const bank = filters;
    return landmarks.slice(0, LANDMARK_COUNT).map((point, index) => ({
      x: bank[index * 3].filter(point.x, t),
      y: bank[index * 3 + 1].filter(point.y, t),
      z: bank[index * 3 + 2].filter(point.z, t),
    }));
  }

  /** Descarta el historial de las manos que ya no están: al reaparecer no se
      interpola desde su última posición conocida. */
  retain(keys: readonly string[]): void {
    for (const key of [...this.filters.keys()]) if (!keys.includes(key)) this.filters.delete(key);
  }

  reset(): void {
    this.filters.clear();
  }
}
