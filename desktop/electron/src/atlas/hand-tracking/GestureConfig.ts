// Umbrales y tiempos del motor de gestos. Módulo puro.

import type { GestureName } from "./types.ts";

export type Band = { enter: number; exit: number };

export type GestureTiming = {
  /** Tiempo que el gesto debe mantenerse antes de confirmarse. */
  minActivationMs: number;
  /** Tiempo tras la confirmación para considerarlo sostenido. */
  holdMs: number;
  /** Pausa obligatoria tras terminar, antes de poder repetirse. */
  cooldownMs: number;
};

export type GestureConfig = {
  /** Relación de aspecto del vídeo: las coordenadas vienen normalizadas por eje. */
  aspect: number;
  open: Band;
  fist: Band;
  pinch: Band;
  spread: Band;
  gather: Band;
  swirl: { windowMs: number; enterAngle: number; exitAngle: number; minRadius: number };
  burst: { windowMs: number; closedMax: number; openMin: number };
  timing: Record<GestureName, GestureTiming>;
  /** Margen durante el que una pérdida de seguimiento no cancela el gesto. */
  lostGraceMs: number;
};

const lerp = (a: number, b: number, t: number) => a + (b - a) * t;

/** Sensibilidad 0 = estricto (menos falsos positivos), 1 = permisivo (más reactivo).
    Cada banda conserva la separación entrada/salida, que es lo que da la histéresis. */
export function gestureConfigFor(sensitivity: number, aspect = 4 / 3): GestureConfig {
  const s = Math.max(0, Math.min(1, sensitivity));
  const time = (ms: number) => Math.round(ms * lerp(1.6, 0.4, s));
  return {
    aspect,
    open: { enter: lerp(0.82, 0.62, s), exit: lerp(0.7, 0.5, s) },
    fist: { enter: lerp(0.14, 0.3, s), exit: lerp(0.26, 0.42, s) },
    // Salida amplia: al arrastrar, el desenfoque separa las puntas en la imagen y
    // el agarre no debe soltarse por eso.
    pinch: { enter: lerp(0.3, 0.5, s), exit: lerp(0.75, 1, s) },
    spread: { enter: lerp(0.62, 0.46, s), exit: lerp(0.54, 0.38, s) },
    gather: { enter: lerp(0.16, 0.26, s), exit: lerp(0.23, 0.34, s) },
    swirl: { windowMs: 1600, enterAngle: Math.PI * lerp(2, 1.3, s), exitAngle: Math.PI * lerp(1.1, 0.7, s), minRadius: lerp(0.045, 0.025, s) },
    burst: { windowMs: lerp(450, 800, s), closedMax: lerp(0.28, 0.42, s), openMin: lerp(0.78, 0.62, s) },
    timing: {
      open_hand: { minActivationMs: time(180), holdMs: 600, cooldownMs: 0 },
      fist: { minActivationMs: time(180), holdMs: 600, cooldownMs: 0 },
      pinch: { minActivationMs: time(120), holdMs: 500, cooldownMs: 400 },
      swirl: { minActivationMs: time(100), holdMs: 800, cooldownMs: 600 },
      spread: { minActivationMs: time(200), holdMs: 600, cooldownMs: 0 },
      gather: { minActivationMs: time(250), holdMs: 600, cooldownMs: 800 },
      // Impulso de un solo fotograma: lo que evita repeticiones es el cooldown.
      burst: { minActivationMs: 0, holdMs: 0, cooldownMs: 2500 },
    },
    lostGraceMs: 350,
  };
}
