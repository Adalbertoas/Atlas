import { STATE_LABELS } from "../interaction/AtlasVisualStateMachine.ts";
import { HANDS_FREE_PRIVACY } from "./ListeningSettings.tsx";
import type { NeuralCore } from "./useNeuralCore.ts";

const CORE_MESSAGES = {
  unavailable: "WebGL no disponible: el nucleo 3D esta desactivado.",
  "context-lost": "Contexto grafico perdido. Recuperando...",
} as const;

/** Indicadores siempre visibles: estado de ATLAS, cámara y micrófono activos
    (con apagado inmediato), lo que se está diciendo y avisos del núcleo. */
export function NeuralCoreHud({ neural, focus, onToggleFocus, onOpenSettings }: { neural: NeuralCore; focus: boolean; onToggleFocus: () => void; onOpenSettings: () => void }) {
  const { runtime, snapshot, settings } = neural;
  const coreMessage = snapshot.core === "unavailable" || snapshot.core === "context-lost" ? CORE_MESSAGES[snapshot.core] : null;

  return <div className="neural-hud" role="status">
    <div className="neural-hud-row">
      <span className={`neural-state state-${snapshot.state.toLowerCase()}`}><i />{STATE_LABELS[snapshot.state]}</span>
      {settings.particles && snapshot.core === "ok" && <button type="button" onClick={onToggleFocus} title="Ocultar o mostrar los paneles para ver el nucleo (Ctrl+Shift+H)">{focus ? "Mostrar paneles" : "Ver nucleo"}</button>}
      {!snapshot.handsFree && <button type="button" onClick={() => void runtime.enableHandsFree()} title={HANDS_FREE_PRIVACY}>Escuchar &quot;Atlas&quot;</button>}
      <button type="button" onClick={onOpenSettings} title="Configuracion de Neural Core">Neural Core</button>
    </div>
    {snapshot.handsFree && snapshot.voice === "standby" && <div className="neural-hud-row neural-device neural-listening">
      <span className="neural-live"><i />Escuchando &quot;Atlas&quot;</span>
      <button type="button" onClick={() => runtime.disableHandsFree()}>Apagar</button>
    </div>}
    {snapshot.camera !== "off" && snapshot.camera !== "error" && <div className="neural-hud-row neural-device">
      <span className="neural-live"><i />{snapshot.camera === "starting" ? "Iniciando camara..." : "Camara activa"}</span>
      <button type="button" onClick={() => runtime.disableHandControl()}>Apagar</button>
    </div>}
    {(snapshot.voice === "recording" || snapshot.voice === "transcribing") && <div className="neural-hud-row neural-device neural-heard">
      <span className="neural-live"><i />{snapshot.voice === "recording" ? "Te escucho" : "Entendiendo"}</span>
      <q className={snapshot.transcript ? "" : "is-empty"}>{snapshot.transcript || "..."}</q>
      {snapshot.voice === "recording" && <button type="button" onClick={() => runtime.cancelMicrophone()}>Descartar</button>}
    </div>}
    {snapshot.voice === "speaking" && <div className="neural-hud-row neural-device">
      <span>ATLAS esta hablando</span>
      <button type="button" onClick={() => runtime.stopSpeaking()}>Silenciar</button>
    </div>}
    {snapshot.voiceNote && <div className="neural-hud-row neural-notice voice-note">{snapshot.voiceNote}</div>}
    {coreMessage && <div className="neural-hud-row neural-notice">{coreMessage}</div>}
    {snapshot.performanceHint && <div className="neural-hud-row neural-notice">
      <span>Rendimiento bajo sostenido.</span>
      <button type="button" onClick={() => runtime.lowerQuality()}>Reducir calidad</button>
    </div>}
    {snapshot.notice && <div className="neural-hud-row neural-notice">
      <span>{snapshot.notice}</span>
      <button type="button" aria-label="Cerrar aviso" onClick={() => runtime.dismissNotice()}>×</button>
    </div>}
  </div>;
}
