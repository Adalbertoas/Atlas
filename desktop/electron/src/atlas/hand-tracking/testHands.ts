// Manos sintéticas para las pruebas: 21 landmarks con una apertura conocida.

import type { HandFrame, Landmark, TrackedHand } from "./types.ts";

export type HandPose = { cx: number; cy: number; open: number; pinch?: boolean };

const lerp = (a: Landmark, b: Landmark, t: number): Landmark => ({ x: a.x + (b.x - a.x) * t, y: a.y + (b.y - a.y) * t, z: 0 });

/** Mano vista de frente con la muñeca abajo. `open` 0 = puño, 1 = extendida.
    Con `pinch`, el pulgar toca la punta del índice y el resto sigue en `open`. */
export function makeHand({ cx, cy, open, pinch = false }: HandPose): TrackedHand {
  const wrist: Landmark = { x: cx, y: cy + 0.12, z: 0 };
  const knuckles: Landmark[] = [
    { x: cx - 0.03, y: cy + 0.02, z: 0 },
    { x: cx, y: cy + 0.02, z: 0 },
    { x: cx + 0.025, y: cy + 0.025, z: 0 },
    { x: cx + 0.05, y: cy + 0.04, z: 0 },
  ];
  const landmarks: Landmark[] = new Array(21);
  landmarks[0] = wrist;
  knuckles.forEach((mcp, finger) => {
    const extension = pinch && finger === 0 ? 0.5 : open;
    // punta→muñeca / nudillo→muñeca va de 1 (plegado) a 1.85 (extendido).
    const tip = lerp(wrist, mcp, 1 + 0.85 * extension);
    const base = 5 + finger * 4;
    landmarks[base] = mcp;
    landmarks[base + 1] = lerp(mcp, tip, 1 / 3);
    landmarks[base + 2] = lerp(mcp, tip, 2 / 3);
    landmarks[base + 3] = tip;
  });
  const thumbBase: Landmark = { x: cx - 0.05, y: cy + 0.08, z: 0 };
  const thumbTip: Landmark = pinch ? { x: landmarks[8].x + 0.005, y: landmarks[8].y, z: 0 } : { x: cx - 0.09, y: cy + 0.04, z: 0 };
  landmarks[1] = lerp(wrist, thumbBase, 0.5);
  landmarks[2] = thumbBase;
  landmarks[3] = lerp(thumbBase, thumbTip, 0.5);
  landmarks[4] = thumbTip;
  return { landmarks, handedness: null };
}

export function frameOf(timestamp: number, ...poses: HandPose[]): HandFrame {
  return { timestamp, hands: poses.map(makeHand) };
}
