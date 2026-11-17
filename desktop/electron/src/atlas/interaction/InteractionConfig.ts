// Preferencias de la sección "Neural Core" y su persistencia. Módulo puro: el
// almacenamiento se inyecta.
//
// El control por manos NO forma parte de estas preferencias a propósito: la
// cámara nunca se enciende sola al abrir ATLAS, hay que activarla en cada sesión.
// La escucha manos libres tampoco se guarda encendida: solo se recuerda si el
// usuario pidió expresamente activarla al iniciar (`listenOnStartup`).

import { GESTURE_NAMES, type GestureName } from "../hand-tracking/types.ts";
import type { QualityLevel } from "../particle-core/ParticlePresets.ts";

export type QualitySetting = "auto" | QualityLevel;

export type NeuralCoreSettings = {
  particles: boolean;
  voiceReaction: boolean;
  /** Leer en voz alta también las respuestas a mensajes escritos. */
  speakReplies: boolean;
  /** Activar la escucha manos libres ("Atlas") al abrir ATLAS. */
  listenOnStartup: boolean;
  /** 0 estricta … 1 capta voz baja. */
  micSensitivity: number;
  /** Tras una respuesta hablada, escuchar unos segundos sin necesidad de "Atlas". */
  followUp: boolean;
  /** Pitido al oír "Atlas". */
  wakeSound: boolean;
  /** En manos libres, obedecer solo a la voz registrada (si hay una registrada). */
  onlyMyVoice: boolean;
  /** Parecido mínimo con la voz registrada, 0,3 (permisivo) … 0,8 (estricto). */
  speakerThreshold: number;
  /** 0 estricto … 1 permisivo. */
  gestureSensitivity: number;
  /** 0..1 */
  intensity: number;
  quality: QualitySetting;
  /** Bajar la calidad sola ante una caída sostenida de FPS (solo en "auto"). */
  autoReduceQuality: boolean;
  /** null = color según el estado de ATLAS. */
  coreColor: string | null;
  energyEffects: boolean;
  /** Solo tiene efecto en calidad alta. */
  bloom: boolean;
  debugLandmarks: boolean;
  /** Mostrar también la imagen de la cámara en la vista de depuración. */
  debugCamera: boolean;
  /** Rotación con las manos: inclinar, agarrar y girar, y volante a dos manos. */
  rotateWithHand: boolean;
  gestures: Record<GestureName, boolean>;
};

export const DEFAULT_SETTINGS: NeuralCoreSettings = {
  particles: true,
  voiceReaction: true,
  speakReplies: false,
  listenOnStartup: false,
  micSensitivity: 0.5,
  followUp: true,
  wakeSound: true,
  onlyMyVoice: true,
  speakerThreshold: 0.5,
  gestureSensitivity: 0.5,
  intensity: 0.75,
  quality: "auto",
  autoReduceQuality: true,
  coreColor: null,
  energyEffects: true,
  bloom: false,
  debugLandmarks: false,
  debugCamera: false,
  rotateWithHand: true,
  gestures: { open_hand: true, fist: true, pinch: true, swirl: true, spread: true, gather: true, burst: true },
};

export const GESTURE_LABELS: Record<GestureName, string> = {
  open_hand: "Mano abierta: expandir",
  fist: "Puño: contraer",
  pinch: "Pinza: agarrar y girar",
  swirl: "Circulos: torbellino",
  spread: "Separar manos: expandir",
  gather: "Juntar manos: reconstruir",
  burst: "Abrir ambas manos rapido: explosion",
};

const QUALITY_VALUES: readonly QualitySetting[] = ["auto", "low", "medium", "high"];

const bool = (value: unknown, fallback: boolean) => (typeof value === "boolean" ? value : fallback);
const unit = (value: unknown, fallback: number) => (typeof value === "number" && Number.isFinite(value) ? Math.max(0, Math.min(1, value)) : fallback);

/** Normaliza lo leído del almacenamiento: tolera datos corruptos, de versiones
    anteriores o manipulados, y nunca lanza. */
export function sanitizeSettings(input: unknown): NeuralCoreSettings {
  const raw = (typeof input === "object" && input !== null ? input : {}) as Record<string, unknown>;
  const d = DEFAULT_SETTINGS;
  const rawGestures = (typeof raw.gestures === "object" && raw.gestures !== null ? raw.gestures : {}) as Record<string, unknown>;
  return {
    particles: bool(raw.particles, d.particles),
    voiceReaction: bool(raw.voiceReaction, d.voiceReaction),
    speakReplies: bool(raw.speakReplies, d.speakReplies),
    listenOnStartup: bool(raw.listenOnStartup, d.listenOnStartup),
    micSensitivity: unit(raw.micSensitivity, d.micSensitivity),
    followUp: bool(raw.followUp, d.followUp),
    wakeSound: bool(raw.wakeSound, d.wakeSound),
    onlyMyVoice: bool(raw.onlyMyVoice, d.onlyMyVoice),
    speakerThreshold: typeof raw.speakerThreshold === "number" && Number.isFinite(raw.speakerThreshold) ? Math.max(0.3, Math.min(0.8, raw.speakerThreshold)) : d.speakerThreshold,
    gestureSensitivity: unit(raw.gestureSensitivity, d.gestureSensitivity),
    intensity: unit(raw.intensity, d.intensity),
    quality: QUALITY_VALUES.includes(raw.quality as QualitySetting) ? (raw.quality as QualitySetting) : d.quality,
    autoReduceQuality: bool(raw.autoReduceQuality, d.autoReduceQuality),
    coreColor: typeof raw.coreColor === "string" && /^#[0-9a-f]{6}$/i.test(raw.coreColor) ? raw.coreColor : null,
    energyEffects: bool(raw.energyEffects, d.energyEffects),
    bloom: bool(raw.bloom, d.bloom),
    debugLandmarks: bool(raw.debugLandmarks, d.debugLandmarks),
    debugCamera: bool(raw.debugCamera, d.debugCamera),
    rotateWithHand: bool(raw.rotateWithHand, d.rotateWithHand),
    gestures: Object.fromEntries(GESTURE_NAMES.map((name) => [name, bool(rawGestures[name], d.gestures[name])])) as Record<GestureName, boolean>,
  };
}

export type SettingsStorage = { getItem(key: string): string | null; setItem(key: string, value: string): void };

export const SETTINGS_KEY = "atlas.neural-core.v1";

export class SettingsStore {
  private readonly storage: SettingsStorage | null;
  private readonly listeners = new Set<() => void>();
  private value: NeuralCoreSettings;

  constructor(storage: SettingsStorage | null) {
    this.storage = storage;
    let stored: unknown = null;
    try {
      stored = JSON.parse(storage?.getItem(SETTINGS_KEY) ?? "null");
    } catch {
      /* se usan los valores predeterminados */
    }
    this.value = sanitizeSettings(stored);
  }

  get = (): NeuralCoreSettings => this.value;

  subscribe = (listener: () => void): (() => void) => {
    this.listeners.add(listener);
    return () => this.listeners.delete(listener);
  };

  update(patch: Partial<NeuralCoreSettings>): void {
    this.commit(sanitizeSettings({ ...this.value, ...patch }));
  }

  reset(): void {
    this.commit(sanitizeSettings(null));
  }

  private commit(next: NeuralCoreSettings): void {
    this.value = next;
    try {
      this.storage?.setItem(SETTINGS_KEY, JSON.stringify(next));
    } catch {
      /* la persistencia es opcional */
    }
    for (const listener of this.listeners) listener();
  }
}
