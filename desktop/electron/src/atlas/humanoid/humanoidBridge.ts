// Traducción entre la aplicación y el humanoide de partículas. Módulo puro (sin DOM ni WebGL).

import type { HandFrame } from "../hand-tracking/types.ts";
import type { AtlasVisualState } from "../interaction/AtlasVisualStateMachine.ts";
import type { QualityLevel } from "../particle-core/ParticlePresets.ts";
import type { HandLandmarkerResult, HumanoidQuality } from "./particles/src/integration/AtlasParticle3D.js";

/** Estados del contrato de Atlas3D que entiende el humanoide. */
export type HumanoidState = "idle" | "listening" | "thinking" | "executing" | "speaking" | "error";

/** Estado visual de ATLAS → estado del humanoide. Sale siempre de un evento real:
    PROCESSING (transcribir o sintetizar voz) se ve como "pensando"; EXECUTING
    solo existe mientras el backend ejecuta una herramienta; SUCCESS y el reposo
    vuelven a la postura de espera. */
export function humanoidState(state: AtlasVisualState): HumanoidState {
  switch (state) {
    case "LISTENING":
      return "listening";
    case "THINKING":
    case "PROCESSING":
      return "thinking";
    case "EXECUTING":
      return "executing";
    case "SPEAKING":
      return "speaking";
    case "ERROR":
      return "error";
    default:
      return "idle";
  }
}

/** El audio solo mueve al humanoide cuando es la voz de quien habla: el
    micrófono al escuchar y la voz de ATLAS al responder. Con la escucha manos
    libres el micrófono queda abierto, y el ruido de fondo no debe animarlo. */
export function audioDrivesHumanoid(state: HumanoidState): boolean {
  return state === "listening" || state === "speaking";
}

export function humanoidQuality(quality: QualityLevel): HumanoidQuality {
  return quality === "low" ? "LOW" : quality === "high" ? "HIGH" : "MEDIUM";
}

/** Los landmarks de la aplicación vienen reflejados (vista de espejo); el
    seguimiento del humanoide espera los de MediaPipe tal cual, en coordenadas de imagen. */
export function toLandmarkerResult(frame: HandFrame): HandLandmarkerResult {
  return {
    landmarks: frame.hands.map((hand) => hand.landmarks.map((point) => ({ x: 1 - point.x, y: point.y, z: point.z }))),
    handedness: frame.hands.map((hand) => (hand.handedness ? [{ categoryName: hand.handedness, score: 1 }] : [])),
  };
}
