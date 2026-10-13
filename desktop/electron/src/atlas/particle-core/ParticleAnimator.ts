// Convierte "qué debería mostrar el núcleo" (preset + gestos + audio) en los
// valores que consumen los shaders, amortiguando cada parámetro para que ningún
// cambio de estado produzca saltos. Módulo puro: sin Three.js ni DOM.

import type { CorePreset, RGB } from "./ParticlePresets.ts";

export type GestureInfluence = {
  /** 0 sin manos, 1 con seguimiento estable. Escala el resto de campos. */
  strength: number;
  /** -1 contraer … 1 expandir. */
  expansion: number;
  yaw: number;
  pitch: number;
  vortex: number;
  /** Punto de interacción en coordenadas de escena (plano z = 0). */
  interaction: readonly [number, number] | null;
  /** Giro acumulado por el usuario al agarrar el núcleo. No depende de
      `strength`: se conserva cuando las manos salen de cámara. */
  spinYaw: number;
  spinPitch: number;
  roll: number;
  grabbing: boolean;
};

export const NO_GESTURE: GestureInfluence = { strength: 0, expansion: 0, yaw: 0, pitch: 0, vortex: 0, interaction: null, spinYaw: 0, spinPitch: 0, roll: 0, grabbing: false };

export type AudioInfluence = { level: number; bass: number; mid: number; treble: number };

export const SILENCE: AudioInfluence = { level: 0, bass: 0, mid: 0, treble: 0 };

export type CoreInputs = {
  preset: CorePreset;
  gesture: GestureInfluence;
  audio: AudioInfluence;
  /** 0..1, preferencia "Intensidad de partículas". */
  intensity: number;
  /** Ondas, pulsos y halo. */
  energyEffects: boolean;
  /** 0..1; respeta la preferencia global "Animaciones". */
  motionScale: number;
  /** Sustituye el color del preset cuando el usuario fija un color propio. */
  tint: RGB | null;
};

export type CoreFrame = {
  time: number;
  colorA: [number, number, number];
  colorB: [number, number, number];
  expansion: number;
  yaw: number;
  pitch: number;
  roll: number;
  brightness: number;
  wavePhase: number;
  waveStrength: number;
  emotion: number;
  jitter: number;
  ring: number;
  cloud: number;
  vortex: number;
  vortexPhase: number;
  explosion: number;
  pulse: number;
  audio: AudioInfluence;
  gestureStrength: number;
  interaction: [number, number, number];
  interactionStrength: number;
  size: number;
  halo: number;
};

/** Amortiguación exponencial independiente de la tasa de fotogramas. */
export function damp(current: number, target: number, lambda: number, dt: number): number {
  return current + (target - current) * (1 - Math.exp(-lambda * dt));
}

const BASE_TILT = 0.18;
const BASE_SIZE = 0.03;
const EXPLOSION_HOLD_S = 1.1;
const PULSE_DURATION_S = 1.1;
const WAVE_SPEED = 3.2;

export class ParticleAnimator {
  private pointScale: number;
  private readonly frame: CoreFrame;
  private autoYaw = 0;
  private waveDirection = 0;
  private explosionTarget = 0;
  private explosionHold = 0;

  constructor(pointScale = 1) {
    this.pointScale = pointScale;
    this.frame = {
      time: 0,
      colorA: [0.2, 0.85, 1],
      colorB: [0.1, 0.45, 1],
      expansion: 1,
      yaw: 0,
      pitch: BASE_TILT,
      roll: 0,
      brightness: 1,
      wavePhase: 0,
      waveStrength: 0,
      emotion: 0.2,
      jitter: 0,
      ring: 0,
      cloud: 0,
      vortex: 0,
      vortexPhase: 0,
      explosion: 0,
      pulse: -1,
      audio: { ...SILENCE },
      gestureStrength: 0,
      interaction: [0, 0, 0],
      interactionStrength: 0,
      size: BASE_SIZE * pointScale,
      halo: 0.3,
    };
  }

  setPointScale(pointScale: number): void {
    this.pointScale = pointScale;
  }

  /** Explosión visual: dispersa las partículas y, tras una pausa, las reconstruye sola. */
  triggerExplosion(): void {
    this.explosionTarget = 1;
    this.explosionHold = EXPLOSION_HOLD_S;
  }

  /** Vuelve a la esfera desde cualquier punto de la explosión, sin saltos. */
  reconstruct(): void {
    this.explosionTarget = 0;
    this.explosionHold = 0;
  }

  triggerPulse(): void {
    this.frame.pulse = 0;
  }

  get exploding(): boolean {
    return this.explosionTarget === 1;
  }

  step(dt: number, inputs: CoreInputs): CoreFrame {
    const f = this.frame;
    const { preset, gesture, audio } = inputs;
    const motion = Math.max(0, Math.min(1, inputs.motionScale));
    const intensity = Math.max(0, Math.min(1, inputs.intensity));
    const energy = inputs.energyEffects ? 1 : 0;
    const g = Math.max(0, Math.min(1, gesture.strength));

    f.time += dt * preset.timeScale * (0.15 + 0.85 * motion);

    const colorA = inputs.tint ?? preset.colorA;
    const colorB = inputs.tint ? mixRgb(inputs.tint, preset.colorB, 0.35) : preset.colorB;
    for (let i = 0; i < 3; i += 1) {
      f.colorA[i] = damp(f.colorA[i], colorA[i], 3, dt);
      f.colorB[i] = damp(f.colorB[i], colorB[i], 3, dt);
    }

    // Mientras el usuario sujeta el núcleo, el giro automático no lo arrastra.
    if (!gesture.grabbing) this.autoYaw += dt * preset.rotationSpeed * motion;
    // El giro por gesto se suma al automático en vez de sustituirlo: al soltar
    // la mano vuelve a 0 y el núcleo sigue girando desde donde estaba.
    f.yaw = damp(f.yaw, this.autoYaw + gesture.spinYaw + gesture.yaw * g, 7, dt);
    f.pitch = damp(f.pitch, BASE_TILT + gesture.spinPitch + gesture.pitch * g, 7, dt);
    f.roll = damp(f.roll, gesture.roll, 7, dt);

    const expansion = preset.expansion + gesture.expansion * 0.45 * g + audio.level * 0.12;
    f.expansion = damp(f.expansion, Math.max(0.45, Math.min(1.7, expansion)), 4, dt);
    f.brightness = damp(f.brightness, preset.brightness * (0.45 + 0.75 * intensity) * (1 + audio.level * 0.35), 4, dt);
    f.emotion = damp(f.emotion, preset.turbulence, 2.5, dt);
    f.jitter = damp(f.jitter, preset.jitter, 6, dt);
    f.ring = damp(f.ring, preset.ring, 2.5, dt);
    f.cloud = damp(f.cloud, preset.cloud, 2.5, dt);
    f.vortex = damp(f.vortex, Math.max(preset.vortex, gesture.vortex * g), 2.2, dt);
    // La fase se integra aquí: multiplicar uTime por un peso variable en el
    // shader haría saltar el giro cada vez que el peso cambia.
    f.vortexPhase += dt * f.vortex * 2.4 * motion;

    this.waveDirection = damp(this.waveDirection, preset.waveDirection, 3, dt);
    f.wavePhase += dt * WAVE_SPEED * this.waveDirection * (0.2 + 0.8 * motion);
    f.waveStrength = damp(f.waveStrength, preset.waveStrength * energy, 3, dt);

    if (this.explosionTarget === 1 && f.explosion > 0.97) {
      this.explosionHold -= dt;
      if (this.explosionHold <= 0) this.explosionTarget = 0;
    }
    f.explosion = damp(f.explosion, this.explosionTarget, this.explosionTarget === 1 ? 9 : 2.4, dt);
    if (this.explosionTarget === 0 && f.explosion < 0.0005) f.explosion = 0;

    if (f.pulse >= 0) {
      f.pulse += dt / PULSE_DURATION_S;
      if (f.pulse > 1 || !inputs.energyEffects) f.pulse = -1;
    }

    f.audio.level = audio.level;
    f.audio.bass = audio.bass;
    f.audio.mid = audio.mid;
    f.audio.treble = audio.treble;

    f.gestureStrength = damp(f.gestureStrength, g, 4, dt);
    if (gesture.interaction) {
      f.interaction[0] = damp(f.interaction[0], gesture.interaction[0], 10, dt);
      f.interaction[1] = damp(f.interaction[1], gesture.interaction[1], 10, dt);
    }
    f.interactionStrength = damp(f.interactionStrength, gesture.interaction ? g : 0, 6, dt);

    f.size = BASE_SIZE * this.pointScale * (0.7 + 0.6 * intensity);
    f.halo = damp(f.halo, energy * (0.16 + 0.22 * intensity) * preset.brightness * (1 + audio.level * 0.8), 3, dt);

    return f;
  }
}

function mixRgb(a: RGB, b: RGB, t: number): RGB {
  return [a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t, a[2] + (b[2] - a[2]) * t];
}
