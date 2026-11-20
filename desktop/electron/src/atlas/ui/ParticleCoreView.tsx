import { Component, useEffect, useRef, useState, useSyncExternalStore, type ReactNode } from "react";
import type { AtlasInteractionController } from "../interaction/AtlasInteractionController.ts";
import "./neural-core.css";

type Marker = { id: number; x: number; y: number };

/** Lienzo del núcleo en la zona central, detrás de los paneles flotantes. */
function CoreCanvas({ runtime }: { runtime: AtlasInteractionController }) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const [marker, setMarker] = useState<Marker | null>(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    const host = canvas?.parentElement;
    if (!canvas || !host) return;
    const detach = runtime.attachCore(canvas);
    const observer = new ResizeObserver(() => runtime.setViewAspect(host.clientWidth / Math.max(1, host.clientHeight)));
    observer.observe(host);
    return () => {
      observer.disconnect();
      detach();
    };
  }, [runtime]);

  // Pinza confirmada: se marca el punto seleccionado sobre el núcleo.
  useEffect(() => {
    let timer = 0;
    runtime.onSelect = (point) => {
      setMarker({ id: performance.now(), x: point.x, y: point.y });
      window.clearTimeout(timer);
      timer = window.setTimeout(() => setMarker(null), 700);
    };
    return () => {
      window.clearTimeout(timer);
      runtime.onSelect = null;
    };
  }, [runtime]);

  return <div className="neural-core-layer" aria-hidden="true">
    <canvas ref={canvasRef} />
    {marker && <i key={marker.id} className="neural-select-marker" style={{ left: `${(marker.x + 1) * 50}%`, top: `${(1 - marker.y) * 50}%` }} />}
  </div>;
}

/** Humanoide de partículas (ATLAS 3D) en el mismo lugar y tamaño que el núcleo:
    AtlasParticle3D crea su propio lienzo dentro de esta capa. */
function HumanoidLayer({ runtime }: { runtime: AtlasInteractionController }) {
  const hostRef = useRef<HTMLDivElement>(null);
  const [marker, setMarker] = useState<Marker | null>(null);

  useEffect(() => {
    const host = hostRef.current;
    if (!host) return;
    const detach = runtime.attachAvatar(host);
    const observer = new ResizeObserver(() => runtime.setViewAspect(host.clientWidth / Math.max(1, host.clientHeight)));
    observer.observe(host);
    return () => {
      observer.disconnect();
      detach();
    };
  }, [runtime]);

  useEffect(() => {
    let timer = 0;
    runtime.onSelect = (point) => {
      setMarker({ id: performance.now(), x: point.x, y: point.y });
      window.clearTimeout(timer);
      timer = window.setTimeout(() => setMarker(null), 700);
    };
    return () => {
      window.clearTimeout(timer);
      runtime.onSelect = null;
    };
  }, [runtime]);

  return <div ref={hostRef} className="neural-core-layer is-humanoid" aria-hidden="true">
    {marker && <i key={marker.id} className="neural-select-marker" style={{ left: `${(marker.x + 1) * 50}%`, top: `${(1 - marker.y) * 50}%` }} />}
  </div>;
}

/** Un fallo del núcleo visual nunca debe tumbar el resto de ATLAS. */
class CoreBoundary extends Component<{ children: ReactNode }, { failed: boolean }> {
  state = { failed: false };

  static getDerivedStateFromError() {
    return { failed: true };
  }

  componentDidCatch(error: unknown) {
    console.warn("[neural-core] La vista del nucleo fallo y se desactivo:", error);
  }

  render() {
    return this.state.failed ? null : this.props.children;
  }
}

export function ParticleCoreView({ runtime, enabled, motion, glow }: { runtime: AtlasInteractionController; enabled: boolean; motion: boolean; glow: number }) {
  useEffect(() => runtime.setEnvironment({ motion, glow }), [runtime, motion, glow]);

  // Cualquier interacción cuenta como actividad: saca al núcleo del reposo.
  useEffect(() => {
    const note = () => runtime.noteActivity();
    window.addEventListener("pointerdown", note);
    window.addEventListener("keydown", note);
    return () => {
      window.removeEventListener("pointerdown", note);
      window.removeEventListener("keydown", note);
    };
  }, [runtime]);

  // Humanoide por defecto; el núcleo anterior queda como opción y como plan B
  // si el humanoide no puede cargarse (sin WebGL2 o sin sus recursos).
  const avatar = useSyncExternalStore(runtime.settings.subscribe, () => runtime.settings.get().avatar);
  const humanoid = useSyncExternalStore(runtime.snapshot.subscribe, () => runtime.snapshot.get().humanoid);
  if (!enabled) return null;
  const useHumanoid = avatar === "humanoid" && humanoid !== "unavailable";
  return <CoreBoundary key={useHumanoid ? "humanoid" : "core"}>{useHumanoid ? <HumanoidLayer runtime={runtime} /> : <CoreCanvas runtime={runtime} />}</CoreBoundary>;
}
