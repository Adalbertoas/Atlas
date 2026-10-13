export type Landmark = { x: number; y: number; z: number };

export type TrackedHand = {
  /** 21 puntos normalizados [0,1], con x ya reflejada (vista de espejo). */
  landmarks: Landmark[];
  handedness: string | null;
};

export type HandFrame = {
  /** Milisegundos, mismo reloj que performance.now(). */
  timestamp: number;
  hands: TrackedHand[];
};

export type GestureName = "open_hand" | "fist" | "pinch" | "swirl" | "spread" | "gather" | "burst";

export const GESTURE_NAMES: readonly GestureName[] = ["open_hand", "fist", "pinch", "swirl", "spread", "gather", "burst"];

/** detected: candidato · confirmed: superó el tiempo mínimo · held: sostenido ·
    ended: terminó de forma natural · lost: se perdió el seguimiento a mitad. */
export type GesturePhase = "detected" | "confirmed" | "held" | "ended" | "lost";

export type GestureEvent = { gesture: GestureName; phase: GesturePhase; timestamp: number };

export type GestureOutput = {
  tracked: boolean;
  handCount: number;
  /** 0 puño … 1 mano abierta (mano principal). */
  openness: number;
  /** Posición de la palma respecto al centro del encuadre, -1..1 (y hacia arriba). */
  pan: { x: number; y: number };
  /** Distancia entre palmas en anchos de imagen; null con una sola mano. */
  handsDistance: number | null;
  /** Ángulo de la línea que une las dos palmas (de izquierda a derecha), en radianes
      con el eje y hacia abajo; null con una sola mano. */
  handsAngle: number | null;
  pinchPoint: { x: number; y: number } | null;
  /** Centro de la palma principal, -1..1 con y hacia arriba y sin zona muerta.
      Es más estable que el punto de pinza, que salta al abrir los dedos. */
  palm: { x: number; y: number } | null;
  /** La segunda mano también está en pinza: agarre a dos manos. */
  twoHandPinch: boolean;
  /** Gestos en fase confirmed o held. */
  active: ReadonlySet<GestureName>;
  events: GestureEvent[];
};
