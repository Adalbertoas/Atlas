import { Range, Select, Toggle } from "../../components/Controls";
import { GESTURE_NAMES } from "../hand-tracking/types.ts";
import { GESTURE_LABELS, type AvatarKind, type NeuralCoreSettings as Settings, type QualitySetting } from "../interaction/InteractionConfig.ts";
import { CameraPermissionControl } from "./CameraPermissionControl.tsx";
import { ListeningSettings } from "./ListeningSettings.tsx";
import { useNeuralLive, type NeuralCore } from "./useNeuralCore.ts";

const QUALITY_OPTIONS: readonly (readonly [QualitySetting, string])[] = [
  ["auto", "Automatica"],
  ["low", "Baja (2.500 particulas)"],
  ["medium", "Media (6.000 particulas)"],
  ["high", "Alta (12.000 particulas)"],
];

// El humanoide tiene sus propias densidades (laboratorio ATLAS 3D, fase 5).
const HUMANOID_QUALITY_OPTIONS: readonly (readonly [QualitySetting, string])[] = [
  ["auto", "Automatica"],
  ["low", "Baja (16.384 particulas)"],
  ["medium", "Media (65.536 particulas)"],
  ["high", "Alta (131.072 particulas)"],
];

const AVATAR_OPTIONS: readonly (readonly [AvatarKind, string])[] = [
  ["humanoid", "Humanoide de particulas"],
  ["core", "Nucleo de particulas (anterior)"],
];

const DEFAULT_CUSTOM_COLOR = "#33d9ff";

type Update = (patch: Partial<Settings>) => void;

function GestureSettings({ settings, update }: { settings: Settings; update: Update }) {
  return <>
    <Range label="Sensibilidad de gestos" min={0} value={Math.round(settings.gestureSensitivity * 100)} onChange={value => update({ gestureSensitivity: value / 100 })} />
    <Toggle label="Girar con las manos (inclinar, agarrar, volante)" value={settings.rotateWithHand} onChange={value => update({ rotateWithHand: value })} />
    {GESTURE_NAMES.map(name => <Toggle key={name} label={GESTURE_LABELS[name]} value={settings.gestures[name]} onChange={value => update({ gestures: { ...settings.gestures, [name]: value } })} />)}
  </>;
}

function PerformanceSettings({ neural, update }: { neural: NeuralCore; update: Update }) {
  const { runtime, snapshot, settings } = neural;
  const live = useNeuralLive(runtime);
  const stats = live.stats;
  const humanoid = settings.avatar === "humanoid" && snapshot.humanoid !== "unavailable";
  return <>
    <Select label="Calidad grafica" value={settings.quality} options={humanoid ? HUMANOID_QUALITY_OPTIONS : QUALITY_OPTIONS} onChange={value => update({ quality: value })} />
    <Toggle label="Reducir calidad si baja el rendimiento" value={settings.autoReduceQuality} disabled={settings.quality !== "auto"} onChange={value => update({ autoReduceQuality: value })} />
    {humanoid
      ? <Toggle label="Bloom (apagalo si va lento: el nucleo del pecho se mantiene)" value={settings.avatarBloom} disabled={snapshot.quality === "low"} onChange={value => update({ avatarBloom: value })} />
      : <Toggle label="Bloom (solo calidad alta)" value={settings.bloom} disabled={snapshot.quality !== "high"} onChange={value => update({ bloom: value })} />}
    <p className="setting-note">
      {stats ? `${Math.round(stats.fps)} FPS · render ${stats.renderMs.toFixed(1)} ms · ${stats.particles.toLocaleString("es")} particulas · calidad ${stats.quality}${stats.bloom ? " + bloom" : ""}` : "Nucleo inactivo."}
      {live.inferenceMs !== null && ` · manos ${live.inferenceMs} ms`}
    </p>
  </>;
}

/** Sección "Neural Core" del panel de Configuración. */
export function NeuralCoreSettings({ neural }: { neural: NeuralCore }) {
  const { runtime, settings } = neural;
  const update: Update = patch => runtime.settings.update(patch);

  return <>
    <h3 className="neural-title">Neural Core</h3>
    <Toggle label="Particulas" value={settings.particles} onChange={value => update({ particles: value })} />
    <Select label="Figura central" value={settings.avatar} options={AVATAR_OPTIONS} onChange={value => update({ avatar: value })} />
    {settings.avatar === "humanoid" && neural.snapshot.humanoid === "unavailable" && <p className="setting-note">El humanoide no pudo cargarse en este equipo: se muestra el nucleo anterior.</p>}
    <CameraPermissionControl neural={neural} />
    <Toggle label="Reaccion a la voz" value={settings.voiceReaction} onChange={value => update({ voiceReaction: value })} />
    <Toggle label="Leer en voz alta las respuestas escritas" value={settings.speakReplies} onChange={value => update({ speakReplies: value })} />
    <ListeningSettings neural={neural} />
    <h3 className="neural-title">Neural Core · Apariencia</h3>
    <Range label="Intensidad de particulas" min={10} value={Math.round(settings.intensity * 100)} onChange={value => update({ intensity: value / 100 })} />
    <Toggle label="Efectos de energia" value={settings.energyEffects} onChange={value => update({ energyEffects: value })} />
    <Toggle label="Color del nucleo personalizado" value={settings.coreColor !== null} onChange={value => update({ coreColor: value ? DEFAULT_CUSTOM_COLOR : null })} />
    {settings.coreColor !== null && <label className="select-row"><span>Color en espera</span><input type="color" value={settings.coreColor} onChange={event => update({ coreColor: event.target.value })} /></label>}

    <h3 className="neural-title">Neural Core · Rendimiento</h3>
    <PerformanceSettings neural={neural} update={update} />

    <h3 className="neural-title">Neural Core · Gestos</h3>
    <GestureSettings settings={settings} update={update} />
    <Toggle label="Mostrar landmarks de depuracion" value={settings.debugLandmarks} onChange={value => update({ debugLandmarks: value })} />
    <Toggle label="Incluir imagen de camara en la depuracion" value={settings.debugCamera} disabled={!settings.debugLandmarks} onChange={value => update({ debugCamera: value })} />

    <div className="neural-actions">
      <button type="button" onClick={() => runtime.triggerPulse()}>Probar pulso</button>
      <button type="button" onClick={() => runtime.triggerExplosion()}>Probar explosion</button>
      <button type="button" onClick={() => runtime.resetOrientation()}>Recolocar nucleo</button>
      <button type="button" onClick={() => runtime.settings.reset()}>Restaurar valores predeterminados</button>
    </div>
  </>;
}
