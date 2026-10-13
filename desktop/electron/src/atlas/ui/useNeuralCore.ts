import { useSyncExternalStore } from "react";
import { AtlasInteractionController, type RuntimeLive, type RuntimeSnapshot } from "../interaction/AtlasInteractionController.ts";
import type { NeuralCoreSettings, SettingsStorage } from "../interaction/InteractionConfig.ts";

export type NeuralCore = { runtime: AtlasInteractionController; snapshot: RuntimeSnapshot; settings: NeuralCoreSettings };

let instance: AtlasInteractionController | null = null;

function safeStorage(): SettingsStorage | null {
  try {
    return window.localStorage;
  } catch {
    return null;
  }
}

/** Una única instancia por ventana: cámara, micrófono y contexto WebGL son
    recursos que no deben duplicarse. */
export function getNeuralCore(): AtlasInteractionController {
  if (!instance) {
    const query = new URLSearchParams(window.location.search);
    // Diagnóstico: ?handDelegate=CPU|GPU fuerza dónde corre la inferencia de manos.
    const delegate = query.get("handDelegate");
    instance = new AtlasInteractionController({
      transport: (channel, input) => window.atlas.invoke(channel, input),
      storage: safeStorage(),
      mediapipeBase: new URL("mediapipe", document.baseURI).href,
      handDelegates: delegate === "CPU" || delegate === "GPU" ? [delegate] : undefined,
    });
    window.addEventListener("beforeunload", () => instance?.dispose());
    // Acceso para diagnóstico manual y pruebas de humo: solo con ?neuralDebug.
    if (query.has("neuralDebug")) {
      (window as unknown as { __ATLAS_NEURAL_CORE__?: AtlasInteractionController }).__ATLAS_NEURAL_CORE__ = instance;
    }
  }
  return instance;
}

export function useNeuralCore(): NeuralCore {
  const runtime = getNeuralCore();
  const snapshot = useSyncExternalStore(runtime.snapshot.subscribe, runtime.snapshot.get);
  const settings = useSyncExternalStore(runtime.settings.subscribe, runtime.settings.get);
  return { runtime, snapshot, settings };
}

/** Telemetría de alta frecuencia (FPS, inferencia, gestos): solo la leen los
    componentes que la muestran, para no re-renderizar toda la aplicación. */
export function useNeuralLive(runtime: AtlasInteractionController): RuntimeLive {
  return useSyncExternalStore(runtime.live.subscribe, runtime.live.get);
}
