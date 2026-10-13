// Medidas geométricas de una mano a partir de sus 21 landmarks. Módulo puro.
// Todo se expresa relativo al tamaño de la palma, así funciona igual con la mano
// cerca o lejos de la cámara.

import type { Landmark } from "./types.ts";

export const WRIST = 0;
export const THUMB_TIP = 4;
export const INDEX_MCP = 5;
export const INDEX_TIP = 8;
export const MIDDLE_MCP = 9;
export const MIDDLE_TIP = 12;
export const RING_MCP = 13;
export const RING_TIP = 16;
export const PINKY_MCP = 17;
export const PINKY_TIP = 20;

const FINGERS: readonly (readonly [number, number])[] = [
  [INDEX_MCP, INDEX_TIP],
  [MIDDLE_MCP, MIDDLE_TIP],
  [RING_MCP, RING_TIP],
  [PINKY_MCP, PINKY_TIP],
];

// punta→muñeca / nudillo→muñeca: ~1.0 con el dedo plegado, ~1.85 extendido.
const CURLED_RATIO = 1;
const EXTENDED_RATIO = 1.85;

export type HandFeatures = {
  palmSize: number;
  /** 0 puño … 1 abierta, media de los cuatro dedos largos. */
  openness: number;
  /** Apertura de corazón, anular y meñique: distingue una pinza de un puño. */
  restOpenness: number;
  /** Distancia pulgar–índice en tamaños de palma. */
  pinchRatio: number;
  center: { x: number; y: number };
  pinchPoint: { x: number; y: number };
};

function distance(a: Landmark, b: Landmark, aspect: number): number {
  return Math.hypot((a.x - b.x) * aspect, a.y - b.y, (a.z - b.z) * aspect);
}

const clamp01 = (value: number) => Math.max(0, Math.min(1, value));

export function extractHandFeatures(landmarks: readonly Landmark[], aspect = 4 / 3): HandFeatures | null {
  if (landmarks.length < 21) return null;
  const wrist = landmarks[WRIST];
  const palmSize = distance(wrist, landmarks[MIDDLE_MCP], aspect);
  if (!(palmSize > 1e-4)) return null;

  const extension = FINGERS.map(([mcp, tip]) => {
    const ratio = distance(landmarks[tip], wrist, aspect) / Math.max(distance(landmarks[mcp], wrist, aspect), 1e-4);
    return clamp01((ratio - CURLED_RATIO) / (EXTENDED_RATIO - CURLED_RATIO));
  });

  const palm = [wrist, landmarks[INDEX_MCP], landmarks[MIDDLE_MCP], landmarks[PINKY_MCP]];
  const thumb = landmarks[THUMB_TIP];
  const index = landmarks[INDEX_TIP];

  return {
    palmSize,
    openness: (extension[0] + extension[1] + extension[2] + extension[3]) / 4,
    restOpenness: (extension[1] + extension[2] + extension[3]) / 3,
    pinchRatio: distance(thumb, index, aspect) / palmSize,
    center: { x: palm.reduce((sum, p) => sum + p.x, 0) / palm.length, y: palm.reduce((sum, p) => sum + p.y, 0) / palm.length },
    pinchPoint: { x: (thumb.x + index.x) / 2, y: (thumb.y + index.y) / 2 },
  };
}
