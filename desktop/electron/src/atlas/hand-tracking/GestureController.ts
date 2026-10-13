// Traduce la salida del reconocedor en influencia sobre el núcleo y en acciones.
// Módulo puro: no conoce Three.js, React ni el asistente.

import type { GestureName, GestureOutput } from "./types.ts";

/** Forma estructuralmente idéntica a GestureInfluence del núcleo; se declara
    aquí para que hand-tracking no importe nada de particle-core. */
export type GestureTargets = {
  strength: number;
  expansion: number;
  yaw: number;
  pitch: number;
  vortex: number;
  interaction: readonly [number, number] | null;
  /** Giro acumulado al agarrar el núcleo. Persiste aunque las manos se vayan. */
  spinYaw: number;
  spinPitch: number;
  roll: number;
  /** Hay una pinza sujetando el núcleo: el giro automático se detiene. */
  grabbing: boolean;
};

export type GestureAction = "select" | "explode" | "reconstruct" | (string & {});

export type GestureBinding = {
  action: GestureAction;
  /** Las acciones sensibles (ejecutar herramientas, cambios destructivos)
      nunca se disparan directamente: pasan por `confirm`. */
  sensitive: boolean;
};

export type GestureActionPayload = { gesture: GestureName; point: { x: number; y: number } | null };

export type GestureControllerOptions = {
  actions: Partial<Record<GestureAction, (payload: GestureActionPayload) => void>>;
  bindings?: Partial<Record<GestureName, GestureBinding>>;
  /** Pide confirmación explícita al usuario. Sin él, las acciones sensibles se descartan. */
  confirm?: (action: GestureAction, payload: GestureActionPayload, proceed: () => void) => void;
};

/** Enlaces por defecto: todos son efectos visuales, ninguno ejecuta herramientas. */
export const DEFAULT_BINDINGS: Partial<Record<GestureName, GestureBinding>> = {
  pinch: { action: "select", sensitive: false },
  burst: { action: "explode", sensitive: false },
  gather: { action: "reconstruct", sensitive: false },
};

const MAX_YAW = 1.2;
const MAX_PITCH = 0.6;
const OPENNESS_DEADZONE = 0.15;
// Arrastrar la pinza de lado a lado del encuadre (2 unidades) gira unos 275°.
const SPIN_GAIN = 2.4;
const MAX_SPIN_PITCH = 1.35;
const MAX_SPIN_SPEED = 6;
// La velocidad de lanzamiento se mide en esta ventana, descartando el final:
// al abrir los dedos para soltar, la mano da un respingo que no es un giro.
const FLING_WINDOW_MS = 400;
const FLING_IGNORE_MS = 90;
const FLING_MIN_SPAN_MS = 60;
// Frenado de la inercia tras soltar, en 1/s.
const SPIN_FRICTION = 1.5;
// Un salto mayor entre dos fotogramas es un cambio de manos, no un giro.
const MAX_ROLL_STEP = 0.6;

const clamp = (value: number, limit: number) => Math.max(-limit, Math.min(limit, value));

/** Encuadre de la escena en z = 0: sitúa el punto de pinza sobre el núcleo. */
export type SceneView = { aspect: number; halfHeight: number; centerY: number };

const damp = (current: number, target: number, lambda: number, dt: number) => current + (target - current) * (1 - Math.exp(-lambda * dt));

export class GestureController {
  private readonly options: GestureControllerOptions;
  private readonly bindings: Partial<Record<GestureName, GestureBinding>>;
  private enabled: Partial<Record<GestureName, boolean>> = {};
  private rotationEnabled = true;
  private target = { strength: 0, expansion: 0, yaw: 0, pitch: 0, vortex: 0, interaction: null as readonly [number, number] | null };
  private readonly spin = { yaw: 0, pitch: 0, roll: 0, yawSpeed: 0, pitchSpeed: 0 };
  private grab: { x: number; y: number; t: number } | null = null;
  private grabTrail: { x: number; y: number; t: number }[] = [];
  private lastHandsAngle: number | null = null;
  private current = { strength: 0, expansion: 0, yaw: 0, pitch: 0, vortex: 0 };
  private view: SceneView = { aspect: 16 / 9, halfHeight: 1.5, centerY: 0 };

  constructor(options: GestureControllerOptions) {
    this.options = options;
    this.bindings = options.bindings ?? DEFAULT_BINDINGS;
  }

  /** Un gesto ausente del mapa se considera habilitado. */
  setEnabled(enabled: Partial<Record<GestureName, boolean>>, rotation = true): void {
    this.enabled = enabled;
    this.rotationEnabled = rotation;
  }

  setView(view: SceneView): void {
    if (view.aspect > 0 && view.halfHeight > 0) this.view = view;
  }

  /** Se llama con cada inferencia (a la frecuencia de la cámara, no del render). */
  ingest(output: GestureOutput, now: number = performance.now()): void {
    const on = (name: GestureName) => this.enabled[name] !== false;
    this.updateSpin(output, now, on("pinch"));

    if (!output.tracked) {
      this.release();
    } else {
      let expansion = 0;
      if (output.handsDistance !== null && (on("spread") || on("gather"))) {
        // Dos manos: la separación manda. 0.2 anchos = contraído, 0.75 = máximo.
        expansion = Math.max(-0.6, Math.min(1, (output.handsDistance - 0.42) / 0.33));
        if (expansion > 0 && !on("spread")) expansion = 0;
        if (expansion < 0 && !on("gather")) expansion = 0;
      } else {
        const centered = (output.openness - 0.5) * 2;
        if (Math.abs(centered) > OPENNESS_DEADZONE) expansion = centered;
        if (expansion > 0 && !on("open_hand")) expansion = 0;
        if (expansion < 0 && !on("fist")) expansion = 0;
      }
      this.target = {
        strength: 1,
        expansion,
        yaw: this.rotationEnabled ? output.pan.x * MAX_YAW : 0,
        pitch: this.rotationEnabled ? -output.pan.y * MAX_PITCH : 0,
        vortex: on("swirl") && output.active.has("swirl") ? 1 : 0,
        interaction: on("pinch") && output.pinchPoint ? [output.pinchPoint.x * this.view.halfHeight * this.view.aspect, output.pinchPoint.y * this.view.halfHeight + this.view.centerY] : null,
      };
    }

    for (const event of output.events) {
      if (event.phase !== "confirmed" || !on(event.gesture)) continue;
      const binding = this.bindings[event.gesture];
      if (binding) this.dispatch(binding, { gesture: event.gesture, point: output.pinchPoint });
    }
  }

  /** Sin manos (o cámara apagada): la influencia vuelve gradualmente a cero. */
  release(): void {
    this.target = { strength: 0, expansion: 0, yaw: 0, pitch: 0, vortex: 0, interaction: null };
    // Se pierde el agarre sin lanzamiento: no hay una suelta que medir.
    this.grab = null;
    this.grabTrail = [];
    this.lastHandsAngle = null;
  }

  /** Devuelve el núcleo a su orientación original. */
  resetOrientation(): void {
    this.spin.yaw = this.spin.pitch = this.spin.roll = this.spin.yawSpeed = this.spin.pitchSpeed = 0;
  }

  /** Pinza = agarrar. Con una mano, el desplazamiento de la palma se convierte en
      giro acumulado. Con las dos manos en pinza, el giro de la línea que las une
      ladea el núcleo, como un volante. */
  private updateSpin(output: GestureOutput, now: number, pinchEnabled: boolean): void {
    const spin = this.spin;
    const grabbing = this.rotationEnabled && pinchEnabled && output.tracked && output.pinchPoint !== null && output.palm !== null;
    const point = grabbing ? output.palm : null;
    const wheel = grabbing && output.twoHandPinch;

    if (point && this.grab && !wheel) {
      spin.yaw += (point.x - this.grab.x) * SPIN_GAIN;
      spin.pitch = clamp(spin.pitch + (point.y - this.grab.y) * SPIN_GAIN, MAX_SPIN_PITCH);
    }
    if (point && !wheel) {
      if (!this.grab) {
        // Agarrar detiene el núcleo: la inercia anterior no sigue bajo la mano.
        spin.yawSpeed = 0;
        spin.pitchSpeed = 0;
        this.grabTrail = [];
      }
      this.grabTrail.push({ x: point.x, y: point.y, t: now });
      while (this.grabTrail.length && now - this.grabTrail[0].t > FLING_WINDOW_MS) this.grabTrail.shift();
    } else if (this.grab && !wheel) {
      this.fling(now);
    }
    if (wheel) this.grabTrail = [];
    this.grab = point ? { x: point.x, y: point.y, t: now } : null;

    const angle = wheel ? output.handsAngle : null;
    if (angle !== null && this.lastHandsAngle !== null) {
      const step = angle - this.lastHandsAngle;
      // El ángulo viene con el eje y hacia abajo: se invierte para que el núcleo
      // gire en el mismo sentido que las manos.
      if (Math.abs(step) < MAX_ROLL_STEP) spin.roll -= step;
    }
    this.lastHandsAngle = angle;
  }

  /** Al soltar, el núcleo hereda la velocidad que llevaba la mano. */
  private fling(now: number): void {
    const trail = this.grabTrail;
    this.grabTrail = [];
    let last = trail.length - 1;
    while (last > 0 && now - trail[last].t < FLING_IGNORE_MS) last -= 1;
    const from = trail[0];
    const to = trail[last];
    if (!from || !to || to.t - from.t < FLING_MIN_SPAN_MS) return;
    const seconds = (to.t - from.t) / 1000;
    this.spin.yawSpeed = clamp(((to.x - from.x) * SPIN_GAIN) / seconds, MAX_SPIN_SPEED);
    this.spin.pitchSpeed = clamp(((to.y - from.y) * SPIN_GAIN) / seconds, MAX_SPIN_SPEED);
  }

  /** Se llama una vez por fotograma de render: interpola hacia el último objetivo. */
  step(dt: number): GestureTargets {
    const c = this.current;
    const t = this.target;
    // Entrada rápida, salida lenta: al perder las manos el núcleo regresa con
    // suavidad a su comportamiento automático.
    c.strength = damp(c.strength, t.strength, t.strength > c.strength ? 6 : 1.6, dt);
    c.expansion = damp(c.expansion, t.expansion, 7, dt);
    c.yaw = damp(c.yaw, t.yaw, 7, dt);
    c.pitch = damp(c.pitch, t.pitch, 7, dt);
    c.vortex = damp(c.vortex, t.vortex, 4, dt);

    const spin = this.spin;
    if (!this.grab) {
      spin.yaw += spin.yawSpeed * dt;
      spin.pitch = clamp(spin.pitch + spin.pitchSpeed * dt, MAX_SPIN_PITCH);
      const friction = Math.exp(-SPIN_FRICTION * dt);
      spin.yawSpeed = Math.abs(spin.yawSpeed) < 0.01 ? 0 : spin.yawSpeed * friction;
      spin.pitchSpeed = Math.abs(spin.pitchSpeed) < 0.01 ? 0 : spin.pitchSpeed * friction;
    }
    return { strength: c.strength, expansion: c.expansion, yaw: c.yaw, pitch: c.pitch, vortex: c.vortex, interaction: t.interaction, spinYaw: spin.yaw, spinPitch: spin.pitch, roll: spin.roll, grabbing: this.grab !== null };
  }

  private dispatch(binding: GestureBinding, payload: GestureActionPayload): void {
    const handler = this.options.actions[binding.action];
    if (!handler) return;
    if (!binding.sensitive) {
      handler(payload);
      return;
    }
    this.options.confirm?.(binding.action, payload, () => handler(payload));
  }
}
