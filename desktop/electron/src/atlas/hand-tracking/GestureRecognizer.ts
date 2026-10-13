// Interpreta landmarks ya suavizados: extrae señales continuas (apertura,
// posición, distancia entre manos) y decide qué gestos están presentes. Cada
// gesto pasa después por su GestureStateMachine. Módulo puro.

import { gestureConfigFor, type Band, type GestureConfig } from "./GestureConfig.ts";
import { GestureStateMachine } from "./GestureStateMachine.ts";
import { extractHandFeatures, type HandFeatures } from "./handFeatures.ts";
import { GESTURE_NAMES, type GestureEvent, type GestureName, type GestureOutput, type HandFrame } from "./types.ts";

/** Comparador con histéresis: entra por un umbral y sale por otro más laxo. */
export class Hysteresis {
  private state = false;

  /** `below`: el gesto se activa cuando el valor baja del umbral de entrada. */
  update(value: number, band: Band, below = false): boolean {
    if (below) {
      if (this.state ? value > band.exit : value < band.enter) this.state = !this.state;
    } else if (this.state ? value < band.exit : value > band.enter) {
      this.state = !this.state;
    }
    return this.state;
  }

  reset(): void {
    this.state = false;
  }
}

type PalmSample = { t: number; x: number; y: number };
type OpenSample = { t: number; min: number; max: number };

const wrapAngle = (angle: number) => Math.atan2(Math.sin(angle), Math.cos(angle));
const PAN_DEADZONE = 0.08;

function deadzone(value: number): number {
  const magnitude = Math.abs(value);
  if (magnitude < PAN_DEADZONE) return 0;
  return (Math.sign(value) * (magnitude - PAN_DEADZONE)) / (1 - PAN_DEADZONE);
}

export class GestureRecognizer {
  private config: GestureConfig;
  private readonly machines: Record<GestureName, GestureStateMachine>;
  private readonly bands: Record<"open" | "fist" | "pinch" | "spread" | "gather" | "swirl", Hysteresis> = {
    open: new Hysteresis(),
    fist: new Hysteresis(),
    pinch: new Hysteresis(),
    spread: new Hysteresis(),
    gather: new Hysteresis(),
    swirl: new Hysteresis(),
  };
  private palmHistory: PalmSample[] = [];
  private openHistory: OpenSample[] = [];

  constructor(config: GestureConfig = gestureConfigFor(0.5)) {
    this.config = config;
    this.machines = Object.fromEntries(
      GESTURE_NAMES.map((name) => [name, new GestureStateMachine(name, config.timing[name], config.lostGraceMs)]),
    ) as Record<GestureName, GestureStateMachine>;
  }

  setConfig(config: GestureConfig): void {
    this.config = config;
    for (const name of GESTURE_NAMES) this.machines[name].configure(config.timing[name], config.lostGraceMs);
  }

  reset(): void {
    for (const name of GESTURE_NAMES) this.machines[name].reset();
    for (const band of Object.values(this.bands)) band.reset();
    this.palmHistory = [];
    this.openHistory = [];
  }

  update(frame: HandFrame): GestureOutput {
    const { config } = this;
    const now = frame.timestamp;
    const hands = frame.hands
      .map((hand) => extractHandFeatures(hand.landmarks, config.aspect))
      .filter((features): features is HandFeatures => features !== null)
      .sort((a, b) => b.palmSize - a.palmSize);
    const primary = hands[0] ?? null;
    const secondary = hands[1] ?? null;
    const tracked = primary !== null;

    const present: Record<GestureName, boolean> = { open_hand: false, fist: false, pinch: false, swirl: false, spread: false, gather: false, burst: false };
    let handsDistance: number | null = null;
    let handsAngle: number | null = null;

    if (primary) {
      present.open_hand = this.bands.open.update(primary.openness, config.open);
      present.fist = this.bands.fist.update(primary.openness, config.fist, true);
      // Un puño también junta pulgar e índice: solo es pinza si el resto de la
      // mano sigue abierta.
      // La condición solo se exige para empezar: una vez agarrado, mover la mano
      // deprisa no debe soltarlo aunque el resto de dedos se vea menos abierto.
      const pinching = this.bands.pinch.update(primary.pinchRatio, config.pinch, true);
      present.pinch = pinching && (this.machines.pinch.engaged || primary.restOpenness > 0.4);
      present.swirl = this.detectSwirl(primary, now);
    } else {
      this.bands.open.reset();
      this.bands.fist.reset();
      this.bands.pinch.reset();
      this.bands.swirl.reset();
      this.palmHistory = [];
    }

    if (primary && secondary) {
      handsDistance = Math.hypot((primary.center.x - secondary.center.x) * config.aspect, primary.center.y - secondary.center.y) / config.aspect;
      // Ordenadas por x para que el ángulo no salte 180° si las manos cambian de orden.
      const [left, right] = primary.center.x <= secondary.center.x ? [primary, secondary] : [secondary, primary];
      handsAngle = Math.atan2(right.center.y - left.center.y, (right.center.x - left.center.x) * config.aspect);
      present.spread = this.bands.spread.update(handsDistance, config.spread);
      present.gather = this.bands.gather.update(handsDistance, config.gather, true);
      present.burst = this.detectBurst(primary, secondary, now);
    } else {
      this.bands.spread.reset();
      this.bands.gather.reset();
      this.openHistory = [];
    }

    const events: GestureEvent[] = [];
    const active = new Set<GestureName>();
    for (const name of GESTURE_NAMES) {
      events.push(...this.machines[name].update(present[name], tracked, now));
      if (this.machines[name].engaged) active.add(name);
    }

    return {
      tracked,
      handCount: hands.length,
      openness: primary?.openness ?? 0.5,
      pan: primary ? { x: deadzone((primary.center.x - 0.5) * 2), y: deadzone((0.5 - primary.center.y) * 2) } : { x: 0, y: 0 },
      handsDistance,
      handsAngle,
      palm: primary ? { x: (primary.center.x - 0.5) * 2, y: (0.5 - primary.center.y) * 2 } : null,
      twoHandPinch: active.has("pinch") && secondary !== null && secondary.pinchRatio < config.pinch.exit && secondary.restOpenness > 0.3,
      pinchPoint: primary && active.has("pinch") ? { x: (primary.pinchPoint.x - 0.5) * 2, y: (0.5 - primary.pinchPoint.y) * 2 } : null,
      active,
      events,
    };
  }

  /** Movimiento circular sostenido: suma el ángulo recorrido por la palma
      alrededor del centro de su propia trayectoria reciente. */
  private detectSwirl(hand: HandFeatures, now: number): boolean {
    const { swirl, aspect } = this.config;
    this.palmHistory.push({ t: now, x: hand.center.x * aspect, y: hand.center.y });
    while (this.palmHistory.length && now - this.palmHistory[0].t > swirl.windowMs) this.palmHistory.shift();
    const samples = this.palmHistory;
    if (samples.length < 8) return this.bands.swirl.update(0, { enter: swirl.enterAngle, exit: swirl.exitAngle });

    let cx = 0;
    let cy = 0;
    for (const sample of samples) {
      cx += sample.x;
      cy += sample.y;
    }
    cx /= samples.length;
    cy /= samples.length;

    let total = 0;
    let radiusSum = 0;
    let radiusSquares = 0;
    let previous = Math.atan2(samples[0].y - cy, samples[0].x - cx);
    for (let i = 0; i < samples.length; i += 1) {
      const dx = samples[i].x - cx;
      const dy = samples[i].y - cy;
      const radius = Math.hypot(dx, dy);
      radiusSum += radius;
      radiusSquares += radius * radius;
      if (i > 0) {
        const angle = Math.atan2(dy, dx);
        total += wrapAngle(angle - previous);
        previous = angle;
      }
    }
    const meanRadius = radiusSum / samples.length;
    const deviation = Math.sqrt(Math.max(radiusSquares / samples.length - meanRadius * meanRadius, 0));
    // Con la mano quieta el ruido gira alrededor del centro sin describir
    // ningún círculo: se exige un radio mínimo y razonablemente constante.
    const circular = meanRadius > swirl.minRadius && deviation < meanRadius * 0.6;
    return this.bands.swirl.update(circular ? Math.abs(total) : 0, { enter: swirl.enterAngle, exit: swirl.exitAngle });
  }

  /** Apertura rápida de ambas manos: las dos estaban cerradas hace un instante
      y ahora están abiertas. Devuelve true un único fotograma. */
  private detectBurst(a: HandFeatures, b: HandFeatures, now: number): boolean {
    const { burst } = this.config;
    const min = Math.min(a.openness, b.openness);
    const max = Math.max(a.openness, b.openness);
    while (this.openHistory.length && now - this.openHistory[0].t > burst.windowMs) this.openHistory.shift();
    const wasClosed = this.openHistory.some((sample) => sample.max <= burst.closedMax);
    if (wasClosed && min >= burst.openMin) {
      this.openHistory = [];
      return true;
    }
    this.openHistory.push({ t: now, min, max });
    return false;
  }
}
