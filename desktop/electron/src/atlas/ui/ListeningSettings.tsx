import { useEffect, useState } from "react";
import { Range, Toggle } from "../../components/Controls";
import { marginForSensitivity, probabilityForSensitivity } from "../voice/SpeechSegmenter.ts";
import type { NeuralCore } from "./useNeuralCore.ts";

// El consentimiento vale para la sesión actual, igual que el de la cámara.
let consentedThisSession = false;

export const HANDS_FREE_PRIVACY =
  "ATLAS mantendra el microfono abierto esperando la palabra \"Atlas\". El sonido se analiza en este equipo; solo las frases con voz se envian al backend local de ATLAS para transcribirlas, y no se guardan.";

/** Nivel del micrófono frente al umbral de voz: sirve para ajustar la sensibilidad. */
function MicrophoneMeter({ neural }: { neural: NeuralCore }) {
  const { runtime, settings } = neural;
  const [levels, setLevels] = useState(runtime.microphoneLevels);
  useEffect(() => {
    const timer = window.setInterval(() => setLevels(runtime.microphoneLevels), 200);
    return () => window.clearInterval(timer);
  }, [runtime]);
  if (!levels) return <p className="setting-note">Abre el microfono para ver su nivel.</p>;
  const toPercent = (db: number) => Math.max(0, Math.min(100, ((db + 80) / 80) * 100));
  if (levels.speechProbability !== null) {
    // Detector neuronal: la barra es el volumen y el color dice si suena a voz.
    const { enterProbability } = probabilityForSensitivity(settings.micSensitivity);
    const speaking = levels.speechProbability >= enterProbability;
    return <div className="mic-meter" title="Barra: volumen. Verde: el detector reconoce voz (el ruido de fondo no cuenta).">
      <div className="mic-meter-bar"><i className={speaking ? "is-voice" : ""} style={{ width: `${toPercent(levels.level)}%` }} /></div>
      <small>{speaking ? "Voz detectada" : levels.level > levels.noiseFloor + 6 ? "Ruido (ignorado)" : "Silencio"} · probabilidad de voz {Math.round(levels.speechProbability * 100)}% (minimo {Math.round(enterProbability * 100)}%)</small>
    </div>;
  }
  const threshold = Math.max(levels.noiseFloor + marginForSensitivity(settings.micSensitivity), -50);
  const speaking = levels.level >= threshold;
  return <div className="mic-meter" title="Barra: nivel actual. Marca: umbral a partir del cual se considera voz.">
    <div className="mic-meter-bar"><i className={speaking ? "is-voice" : ""} style={{ width: `${toPercent(levels.level)}%` }} /><b style={{ left: `${toPercent(threshold)}%` }} /></div>
    <small>{speaking ? "Voz detectada" : "Silencio"} · fondo {Math.round(levels.noiseFloor)} dB · umbral {Math.round(threshold)} dB (deteccion por volumen)</small>
  </div>;
}

const ENROLL_PHRASES = [
  "Hola Atlas, esta es mi voz y quiero que la reconozcas.",
  "Me gusta escuchar musica mientras organizo mis tareas del dia.",
  "Atlas, recuerdame revisar el correo manana por la manana.",
];

type EnrollStep = { index: number; samples: Float32Array[]; status: "recording" | "saving"; error: string | null };

/** "Solo responder a mi voz": registro de la huella de voz y su ajuste. */
function VoiceprintSettings({ neural }: { neural: NeuralCore }) {
  const { runtime, snapshot, settings } = neural;
  const [step, setStep] = useState<EnrollStep | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [lastScore, setLastScore] = useState(runtime.lastSpeakerScore);
  const voiceprint = snapshot.voiceprint;
  useEffect(() => {
    void runtime.refreshVoiceprint();
    const timer = window.setInterval(() => setLastScore(runtime.lastSpeakerScore), 500);
    return () => {
      window.clearInterval(timer);
      runtime.cancelVoiceSample();
    };
  }, [runtime]);

  const record = async (index: number, samples: Float32Array[]) => {
    setStep({ index, samples, status: "recording", error: null });
    let sample: Float32Array;
    try {
      sample = await runtime.recordVoiceSample();
    } catch (reason) {
      const message = reason instanceof Error ? reason.message : String(reason);
      if (message !== "Grabacion cancelada.") setStep({ index, samples, status: "recording", error: message });
      return;
    }
    const next = [...samples, sample];
    if (index + 1 < ENROLL_PHRASES.length) {
      void record(index + 1, next);
      return;
    }
    setStep({ index, samples: next, status: "saving", error: null });
    try {
      await runtime.enrollVoice(next);
      setStep(null);
      runtime.settings.update({ onlyMyVoice: true });
    } catch (reason) {
      setStep(null);
      setError(reason instanceof Error ? reason.message.replace(/^Error invoking remote method '[^']+': Error: /, "") : String(reason));
    }
  };
  const start = () => {
    setError(null);
    void record(0, []);
  };
  const cancel = () => {
    runtime.cancelVoiceSample();
    setStep(null);
  };
  const remove = async () => {
    setError(null);
    try {
      await runtime.deleteVoice();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason));
    }
  };

  if (voiceprint === null) return <p className="setting-note">Solo mi voz: el backend de ATLAS no responde.</p>;
  if (!voiceprint.available) return <p className="setting-note">Solo mi voz: falta el modelo de huella de voz. En <code>backend/</code> ejecuta <code>python scripts/download_speaker_model.py</code>.</p>;

  return <>
    {step && <div className="neural-consent voice-enroll" role="status">
      {step.status === "saving" ? <p>Guardando tu huella de voz...</p> : <>
        <p>Frase {step.index + 1} de {ENROLL_PHRASES.length}. Lee en voz alta, con tu voz normal:</p>
        <blockquote>{ENROLL_PHRASES[step.index]}</blockquote>
        <p className={step.error ? "offline-text" : "voice-enroll-live"}>{step.error ?? "Escuchando... se graba sola al terminar la frase."}</p>
        <div>{step.error && <button type="button" className="primary" onClick={() => void record(step.index, step.samples)}>Repetir esta frase</button>}<button type="button" onClick={cancel}>Cancelar</button></div>
      </>}
    </div>}
    {!step && !voiceprint.enrolled && <div className="neural-consent">
      <p>Registra tu voz para que, en manos libres, ATLAS solo obedezca cuando hables tu. Leeras {ENROLL_PHRASES.length} frases cortas. Se guarda una huella numerica en el backend local, no el audio, y puedes borrarla cuando quieras.</p>
      <div><button type="button" className="primary" onClick={start}>Registrar mi voz</button></div>
    </div>}
    {!step && voiceprint.enrolled && <>
      <Toggle label="Solo responder a mi voz (manos libres)" value={settings.onlyMyVoice} onChange={value => runtime.settings.update({ onlyMyVoice: value })} />
      <Range label="Exigencia del reconocimiento de voz" min={30} max={80} value={Math.round(settings.speakerThreshold * 100)} onChange={value => runtime.settings.update({ speakerThreshold: value / 100 })} />
      <p className="setting-note">
        Voz registrada ({voiceprint.samples} frases{voiceprint.consistency !== null ? `, coherencia ${voiceprint.consistency.toFixed(2)}` : ""}).
        {lastScore !== null && <> Ultima frase: <b className={lastScore >= settings.speakerThreshold ? "online-text" : "offline-text"}>{lastScore.toFixed(2)} {lastScore >= settings.speakerThreshold ? "(tu voz)" : "(otra voz)"}</b>; el minimo es {settings.speakerThreshold.toFixed(2)}.</>}
        {" "}El boton del microfono no se filtra.
      </p>
      <div className="neural-actions"><button type="button" onClick={start}>Volver a registrar</button><button type="button" onClick={() => void remove()}>Borrar mi voz</button></div>
    </>}
    {error && <p className="setting-note offline-text">{error}</p>}
  </>;
}

/** Sección "Voz" del panel de Configuración. */
export function ListeningSettings({ neural }: { neural: NeuralCore }) {
  const { runtime, snapshot, settings } = neural;
  const [asking, setAsking] = useState(false);
  const update = (patch: Parameters<typeof runtime.settings.update>[0]) => runtime.settings.update(patch);

  const enable = () => {
    consentedThisSession = true;
    setAsking(false);
    void runtime.enableHandsFree();
  };
  const toggle = (value: boolean) => {
    if (!value) {
      setAsking(false);
      runtime.disableHandsFree();
    } else if (consentedThisSession) enable();
    else setAsking(true);
  };

  return <>
    <h3 className="neural-title">Neural Core · Voz</h3>
    <Toggle label="Escucha manos libres (di &quot;Atlas&quot;)" value={snapshot.handsFree || asking} onChange={toggle} />
    {asking && <div className="neural-consent">
      <p>{HANDS_FREE_PRIVACY} Podras apagarlo en cualquier momento desde el indicador en pantalla.</p>
      <div><button type="button" className="primary" onClick={enable}>Activar escucha</button><button type="button" onClick={() => setAsking(false)}>Cancelar</button></div>
    </div>}
    <Toggle label="Activar la escucha al abrir ATLAS" value={settings.listenOnStartup} onChange={value => update({ listenOnStartup: value })} />
    <Toggle label="Seguir escuchando tras responder (sin repetir &quot;Atlas&quot;)" value={settings.followUp} onChange={value => update({ followUp: value })} />
    <Toggle label="Sonido al oir &quot;Atlas&quot;" value={settings.wakeSound} onChange={value => update({ wakeSound: value })} />
    <Range label="Sensibilidad del microfono" min={0} value={Math.round(settings.micSensitivity * 100)} onChange={value => update({ micSensitivity: value / 100 })} />
    <MicrophoneMeter neural={neural} />
    <h3 className="neural-title">Neural Core · Solo mi voz</h3>
    <VoiceprintSettings neural={neural} />
    <p className="setting-note">Di &quot;Atlas&quot; y tu pedido de un tiron (&quot;Atlas, que hora es&quot;) o &quot;Atlas&quot;, una pausa, y el pedido. El microfono del chat escucha sin necesidad del nombre y envia solo al callarte.</p>
  </>;
}
