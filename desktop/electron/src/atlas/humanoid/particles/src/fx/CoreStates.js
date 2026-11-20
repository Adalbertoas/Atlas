// ATLAS Fase 5E — estados visuales del núcleo. Cada estado es un conjunto de objetivos; el núcleo se acerca a ellos con
// suavizado exponencial, así que cualquier cambio de estado (también interrumpir uno a mitad) es continuo.
// Colores en hexadecimal sRGB; el resto son números (sin unidades salvo indicación).

export const STATES = ["idle", "listening", "thinking", "executing", "speaking", "error"];

export const CORE_PRESETS = {
  idle: {
    color: 0x38d6ff, color2: 0x1a5cff, intensity: 0.65, turb: 0.15, pulseRate: 0.55, pulseAmp: 0.35,
    pulseSine: 1, pulseIrregular: 0, pulseWarn: 0, pulseAudio: 0,
    orbitSpeed: 0.35, ringSpeed: 0.18, noiseSpeed: 0.6, flow: 0, fieldSwirl: 0.15,
    waveRate: 0.12, waveDir: 1, waveAmp: 0.25, audioGain: 0, bodyTint: 0x38d6ff, bodyTintMix: 0, bodyEnergy: 0.15,
  },
  listening: {
    color: 0x4ff0ff, color2: 0x00b3ff, intensity: 0.95, turb: 0.25, pulseRate: 1.0, pulseAmp: 0.3,
    pulseSine: 0.6, pulseIrregular: 0, pulseWarn: 0, pulseAudio: 0.6,
    orbitSpeed: 0.7, ringSpeed: 0.5, noiseSpeed: 1.0, flow: 0, fieldSwirl: 0.4,
    waveRate: 0.9, waveDir: -1, waveAmp: 0.5, audioGain: 1.0, bodyTint: 0x4ff0ff, bodyTintMix: 0, bodyEnergy: 0.35,
  },
  thinking: {
    color: 0x8a7dff, color2: 0x3a5bff, intensity: 1.05, turb: 0.5, pulseRate: 2.1, pulseAmp: 0.45,
    pulseSine: 0.2, pulseIrregular: 1, pulseWarn: 0, pulseAudio: 0,
    orbitSpeed: 1.9, ringSpeed: 1.1, noiseSpeed: 2.2, flow: 0, fieldSwirl: 1.2,
    waveRate: 0.35, waveDir: 1, waveAmp: 0.3, audioGain: 0, bodyTint: 0x8a7dff, bodyTintMix: 0.12, bodyEnergy: 0.4,
  },
  executing: {
    color: 0xffb547, color2: 0xff6a1f, intensity: 1.25, turb: 0.35, pulseRate: 2.6, pulseAmp: 0.4,
    pulseSine: 0.7, pulseIrregular: 0.3, pulseWarn: 0, pulseAudio: 0,
    orbitSpeed: 2.6, ringSpeed: 1.8, noiseSpeed: 1.8, flow: 1, fieldSwirl: 0.8,
    waveRate: 0.8, waveDir: 1, waveAmp: 0.45, audioGain: 0, bodyTint: 0xffb547, bodyTintMix: 0.18, bodyEnergy: 0.5,
  },
  speaking: {
    color: 0x9fe8ff, color2: 0x38a8ff, intensity: 1.0, turb: 0.22, pulseRate: 0.9, pulseAmp: 0.55,
    pulseSine: 0.15, pulseIrregular: 0, pulseWarn: 0, pulseAudio: 1,
    orbitSpeed: 0.9, ringSpeed: 0.7, noiseSpeed: 1.2, flow: 0, fieldSwirl: 0.5,
    waveRate: 0, waveDir: 1, waveAmp: 0.6, audioGain: 1.4, bodyTint: 0x9fe8ff, bodyTintMix: 0, bodyEnergy: 0.55,
  },
  error: {
    color: 0xff3b3b, color2: 0xff7a2f, intensity: 1.15, turb: 0.6, pulseRate: 1.5, pulseAmp: 0.7,
    pulseSine: 0, pulseIrregular: 0, pulseWarn: 1, pulseAudio: 0,
    orbitSpeed: 0.5, ringSpeed: 0.3, noiseSpeed: 2.6, flow: 0, fieldSwirl: 0.1,
    waveRate: 1.5, waveDir: 1, waveAmp: 0.55, audioGain: 0, bodyTint: 0xff3b3b, bodyTintMix: 0.35, bodyEnergy: 0.6,
  },
};

/** Tiempos de transición (constante de tiempo, s) hacia cada estado. ERROR entra rápido; salir de él es suave. */
export const ENTER_TAU = { idle: 0.6, listening: 0.35, thinking: 0.4, executing: 0.3, speaking: 0.3, error: 0.15 };
export const LEAVE_ERROR_TAU = 0.9;

/** Controles del usuario (multiplicadores sobre el estado). */
export const DEFAULT_CONTROLS = { intensity: 1, speed: 1, size: 1, density: 1, brightness: 1, waveAmplitude: 1, color: null, colorMix: 1 };
