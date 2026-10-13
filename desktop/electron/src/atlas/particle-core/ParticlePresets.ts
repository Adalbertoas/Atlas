// Presets visuales y perfiles de calidad del núcleo. Módulo puro: sin Three.js ni DOM.

export type RGB = readonly [number, number, number];

export type QualityLevel = "low" | "medium" | "high";

export type QualityProfile = {
  level: QualityLevel;
  particleCount: number;
  /** Tope de devicePixelRatio: el coste de relleno crece con su cuadrado. */
  maxPixelRatio: number;
  /** Ruido simplex en el vertex shader; en LOW se usa solo el flujo trigonométrico. */
  simplexNoise: boolean;
  bloomAllowed: boolean;
  /** Con menos partículas se agrandan para conservar la densidad aparente. */
  pointScale: number;
};

export const QUALITY_PROFILES: Record<QualityLevel, QualityProfile> = {
  low: { level: "low", particleCount: 2500, maxPixelRatio: 1, simplexNoise: false, bloomAllowed: false, pointScale: 1.4 },
  medium: { level: "medium", particleCount: 6000, maxPixelRatio: 1.5, simplexNoise: true, bloomAllowed: false, pointScale: 1 },
  high: { level: "high", particleCount: 12000, maxPixelRatio: 2, simplexNoise: true, bloomAllowed: true, pointScale: 0.85 },
};

export const QUALITY_ORDER: readonly QualityLevel[] = ["low", "medium", "high"];

export function nextLowerQuality(level: QualityLevel): QualityLevel | null {
  const index = QUALITY_ORDER.indexOf(level);
  return index > 0 ? QUALITY_ORDER[index - 1] : null;
}

/** Calidad inicial en modo automático. Nunca elige HIGH por su cuenta: una GPU
    dedicada no garantiza que el equipo rinda, así que se parte de MEDIUM y el
    monitor de rendimiento baja si hace falta. */
export function pickInitialQuality(rendererName: string | null): QualityLevel {
  if (rendererName && /swiftshader|llvmpipe|software|basic render/i.test(rendererName)) return "low";
  return "medium";
}

export type PresetName = "idle" | "listening" | "thinking" | "speaking" | "processing" | "success" | "error" | "sleeping";

export type CorePreset = {
  colorA: RGB;
  colorB: RGB;
  /** rad/s de giro automático. */
  rotationSpeed: number;
  timeScale: number;
  expansion: number;
  brightness: number;
  /** -1 ondas hacia el centro, 1 hacia fuera, 0 sin dirección. */
  waveDirection: number;
  waveStrength: number;
  turbulence: number;
  /** Vibración de alta frecuencia y baja amplitud (estado de error). */
  jitter: number;
  ring: number;
  cloud: number;
  vortex: number;
};

const base: CorePreset = {
  colorA: [0.2, 0.85, 1],
  colorB: [0.1, 0.45, 1],
  rotationSpeed: 0.12,
  timeScale: 1,
  expansion: 1,
  brightness: 1,
  waveDirection: 0,
  waveStrength: 0.15,
  turbulence: 0.2,
  jitter: 0,
  ring: 0,
  cloud: 0,
  vortex: 0,
};

export const VISUAL_PRESETS: Record<PresetName, CorePreset> = {
  idle: base,
  listening: { ...base, colorA: [0.15, 0.95, 0.78], colorB: [0.05, 0.65, 0.85], waveDirection: -1, waveStrength: 0.7, expansion: 1.04, brightness: 1.1 },
  thinking: { ...base, colorA: [0.66, 0.45, 1], colorB: [0.35, 0.3, 0.95], rotationSpeed: 0.32, timeScale: 1.3, turbulence: 0.85, cloud: 0.35, waveStrength: 0.1 },
  speaking: { ...base, colorA: [0.25, 0.55, 1], colorB: [0.45, 0.85, 1], waveDirection: 1, waveStrength: 0.8, brightness: 1.25, expansion: 1.03 },
  processing: { ...base, colorA: [0.82, 0.92, 1], colorB: [0.55, 0.78, 1], rotationSpeed: 0.85, timeScale: 2.4, turbulence: 0.45, ring: 0.25 },
  success: { ...base, colorA: [0.3, 1, 0.55], colorB: [0.1, 0.8, 0.6], brightness: 1.2, waveDirection: 1, waveStrength: 0.4 },
  error: { ...base, colorA: [1, 0.42, 0.42], colorB: [0.95, 0.25, 0.35], jitter: 0.8, rotationSpeed: 0.05, brightness: 1.05 },
  sleeping: { ...base, colorA: [0.16, 0.32, 0.62], colorB: [0.08, 0.18, 0.45], rotationSpeed: 0.03, timeScale: 0.25, expansion: 0.92, brightness: 0.45, waveStrength: 0.05, turbulence: 0.08 },
};

export function hexToRgb(hex: string): RGB | null {
  const match = /^#?([0-9a-f]{6})$/i.exec(hex.trim());
  if (!match) return null;
  const value = Number.parseInt(match[1], 16);
  return [((value >> 16) & 255) / 255, ((value >> 8) & 255) / 255, (value & 255) / 255];
}
