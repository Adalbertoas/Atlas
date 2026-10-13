import { useState } from "react";
import { Toggle } from "../../components/Controls";
import type { NeuralCore } from "./useNeuralCore.ts";

// El consentimiento vale para la sesión actual; no se guarda entre ejecuciones.
let consentedThisSession = false;

/** Activación explícita de la cámara para el control por manos. */
export function CameraPermissionControl({ neural }: { neural: NeuralCore }) {
  const { runtime, snapshot } = neural;
  const [asking, setAsking] = useState(false);
  const on = snapshot.camera === "starting" || snapshot.camera === "active";

  const enable = () => {
    consentedThisSession = true;
    setAsking(false);
    void runtime.enableHandControl();
  };
  const toggle = (value: boolean) => {
    if (!value) {
      setAsking(false);
      runtime.disableHandControl();
    } else if (consentedThisSession) enable();
    else setAsking(true);
  };

  return <>
    <Toggle label="Control por manos (camara)" value={on || asking} onChange={toggle} />
    {asking && <div className="neural-consent">
      <p>ATLAS usara la camara para detectar tus manos. La imagen se procesa en este equipo: no se guarda ni se envia a ningun servicio. Podras apagarla en cualquier momento desde el indicador en pantalla.</p>
      <div><button type="button" className="primary" onClick={enable}>Activar camara</button><button type="button" onClick={() => setAsking(false)}>Cancelar</button></div>
    </div>}
    {snapshot.camera === "error" && <p className="setting-note offline-text">La camara no esta disponible. ATLAS sigue funcionando sin ella.</p>}
  </>;
}
