// Humanoide de partículas (laboratorio ATLAS 3D, fase 5) dentro de la aplicación.
//
// Envuelve AtlasParticle3D, el adaptador "drop-in" del laboratorio, sin modificarlo:
//   new AtlasParticle3D(container) · setState(state) · setAudioSamples(Uint8Array) · dispose()
// y lo conecta al sistema que ya tiene ATLAS. No abre cámara ni micrófono ni habla con
// el backend: estados, audio y manos llegan del AtlasInteractionController, que sigue
// siendo el único dueño de la voz y de la cámara.

import type { HandFrame } from "../hand-tracking/types.ts";
import type { AtlasVisualState } from "../interaction/AtlasVisualStateMachine.ts";
import type { CoreStats } from "../particle-core/ParticleCore.ts";
import type { QualityLevel } from "../particle-core/ParticlePresets.ts";
import { PerformanceMonitor } from "../particle-core/PerformanceMonitor.ts";
import { audioDrivesHumanoid, humanoidQuality, humanoidState, toLandmarkerResult, type HumanoidState } from "./humanoidBridge.ts";
import { AtlasParticle3D, type HandLandmarkerResult, type HandProvider, type HumanoidAvatar } from "./particles/src/integration/AtlasParticle3D.js";

export type HumanoidFrame = { state: AtlasVisualState; audio: Uint8Array | null };

export type HumanoidCoreOptions = {
  container: HTMLElement;
  /** Carpeta con ATLAS_humanoid_v004.glb y atlas_v004_particles.{bin,json}. */
  assetBase: string;
  quality: QualityLevel;
  bloom: boolean;
  /** Se llama una vez por fotograma, dentro del bucle del humanoide. */
  provideFrame: () => HumanoidFrame;
  onReady?: (rendererName: string | null) => void;
  onUnavailable?: (error: Error) => void;
  onStats?: (stats: CoreStats) => void;
  onPerformanceDegraded?: (quality: QualityLevel) => void;
  onContextLost?: () => void;
  onContextRestored?: () => void;
};

const STATS_INTERVAL_MS = 500;
// Cuerpo entero, centrado algo por encima de la mitad (como el núcleo anterior,
// al 42 % de la altura) para que asome sobre el panel de chat.
const CAMERA = { fov: 30, position: [0, 1.05, 4.9] as [number, number, number], target: [0, 0.82, 0] as [number, number, number] };

/** Puente de manos: el humanoide recibe los landmarks que ya produce la cámara de ATLAS. */
class AppHandProvider implements HandProvider {
  name = "ATLAS";
  status = "stopped";
  onResult: ((result: HandLandmarkerResult, tMs: number) => void) | null = null;

  start(): boolean {
    this.status = "running";
    return true;
  }

  push(frame: HandFrame): void {
    if (this.status === "running") this.onResult?.(toLandmarkerResult(frame), frame.timestamp);
  }

  dispose(): void {
    this.status = "stopped";
    this.onResult = null;
  }
}

export class HumanoidCore {
  private readonly options: HumanoidCoreOptions;
  private readonly view: AtlasParticle3D;
  private readonly monitor = new PerformanceMonitor();
  private avatar: HumanoidAvatar | null = null;
  private hands: AppHandProvider | null = null;
  private handsWanted = false;
  private quality: QualityLevel;
  private bloom: boolean;
  private state: HumanoidState = "idle";
  private lastFrameAt = 0;
  private lastStats = 0;
  private renderMs = 0;
  private disposed = false;
  private stopPixelRatioWatch: (() => void) | null = null;

  constructor(options: HumanoidCoreOptions) {
    this.options = options;
    this.quality = options.quality;
    this.bloom = options.bloom;
    const base = options.assetBase.endsWith("/") ? options.assetBase : `${options.assetBase}/`;
    this.view = new AtlasParticle3D(options.container, {
      glbUrl: `${base}ATLAS_humanoid_v004.glb`,
      dataUrl: `${base}atlas_v004_particles`,
      quality: humanoidQuality(options.quality),
      bloom: options.bloom ? "auto" : "off",
      camera: CAMERA,
      onready: () => this.handleReady(),
      onerror: (error) => {
        if (!this.disposed) options.onUnavailable?.(error);
      },
    });
    this.view.canvas.addEventListener("webglcontextlost", this.handleContextLost);
    this.view.canvas.addEventListener("webglcontextrestored", this.handleContextRestored);
  }

  get ready(): boolean {
    return this.avatar !== null;
  }

  get rendererName(): string | null {
    const gl = this.avatar?.engine.renderer.getContext();
    if (!gl) return null;
    const info = gl.getExtension("WEBGL_debug_renderer_info");
    return info ? String(gl.getParameter(info.UNMASKED_RENDERER_WEBGL)) : String(gl.getParameter(gl.RENDERER));
  }

  /** Para la prueba de que solo hay un humanoide: el lienzo que dibuja este. */
  get canvas(): HTMLCanvasElement {
    return this.view.canvas;
  }

  setQuality(quality: QualityLevel): void {
    if (quality === this.quality) return;
    this.quality = quality;
    this.avatar?.setQuality(humanoidQuality(quality));
    this.monitor.reset(performance.now());
  }

  /** Bloom apagado no quita el núcleo de energía: solo el resplandor de postproceso. */
  setBloom(enabled: boolean): void {
    if (enabled === this.bloom) return;
    this.bloom = enabled;
    this.avatar?.setBloom(enabled ? "auto" : "off");
    this.monitor.reset(performance.now());
  }

  /** La cámara de ATLAS está encendida (true) o apagada (false). */
  setHandsActive(active: boolean): void {
    this.handsWanted = active;
    if (this.avatar) void this.syncHands();
  }

  pushHands(frame: HandFrame): void {
    this.hands?.push(frame);
  }

  // Efectos del núcleo anterior que el humanoide no tiene: se ignoran a propósito.
  start(): void {}
  triggerPulse(): void {}
  triggerExplosion(): void {}
  reconstruct(): void {}

  dispose(): void {
    if (this.disposed) return;
    this.disposed = true;
    this.view.canvas.removeEventListener("webglcontextlost", this.handleContextLost);
    this.view.canvas.removeEventListener("webglcontextrestored", this.handleContextRestored);
    this.stopPixelRatioWatch?.();
    this.hands = null;
    this.avatar = null;
    this.view.dispose();
  }

  private handleReady(): void {
    const avatar = this.view.avatar;
    if (this.disposed || !avatar) return;
    this.avatar = avatar;
    this.view.setState(this.state);
    // La capa se compone con mix-blend-mode: screen: el negro puro es transparente.
    avatar.engine.renderer.setClearColor(0x000000, 1);
    // Cada fotograma del bucle del humanoide recoge antes el estado y el audio
    // reales: un solo requestAnimationFrame, que ya se pausa con la ventana oculta
    // y con el contexto WebGL perdido.
    const update = avatar.update.bind(avatar);
    const render = avatar.render.bind(avatar);
    let frameStart = 0;
    avatar.update = (dt: number) => {
      frameStart = performance.now();
      this.feed();
      update(dt);
    };
    avatar.render = (scene: unknown, camera: unknown) => {
      render(scene, camera);
      this.afterFrame(performance.now() - frameStart);
    };
    this.watchPixelRatio();
    this.monitor.reset(performance.now());
    if (this.handsWanted) void this.syncHands();
    this.options.onReady?.(this.rendererName);
  }

  /** El motor fija el pixel ratio al crearse; si cambia (otra pantalla, zoom del
      sistema) se actualiza para que la imagen siga nítida. Mismo tope de 2 que el motor. */
  private watchPixelRatio(): void {
    this.stopPixelRatioWatch?.();
    const query = window.matchMedia(`(resolution: ${window.devicePixelRatio || 1}dppx)`);
    const onChange = () => {
      this.avatar?.engine.renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
      this.monitor.reset(performance.now());
      if (!this.disposed) this.watchPixelRatio();
    };
    query.addEventListener("change", onChange, { once: true });
    this.stopPixelRatioWatch = () => query.removeEventListener("change", onChange);
  }

  private feed(): void {
    const frame = this.options.provideFrame();
    const next = humanoidState(frame.state);
    if (next !== this.state) {
      this.state = next;
      this.view.setState(next);
    }
    if (frame.audio && audioDrivesHumanoid(next)) this.view.setAudioSamples(frame.audio);
  }

  private afterFrame(workMs: number): void {
    const now = performance.now();
    const frameMs = this.lastFrameAt ? now - this.lastFrameAt : 0;
    this.lastFrameAt = now;
    this.renderMs += (workMs - this.renderMs) * 0.1;
    if (this.monitor.sample(frameMs, now)) this.options.onPerformanceDegraded?.(this.quality);
    if (now - this.lastStats >= STATS_INTERVAL_MS && this.avatar) {
      this.lastStats = now;
      this.options.onStats?.({ fps: this.monitor.fps, renderMs: this.renderMs, particles: this.avatar.engine.count, quality: this.quality, bloom: this.avatar.engine.bloomOn });
    }
  }

  private async syncHands(): Promise<void> {
    const avatar = this.avatar;
    if (!avatar) return;
    if (this.handsWanted && !this.hands) {
      const provider = new AppHandProvider();
      this.hands = provider;
      await avatar.enableHandInput({ provider });
    } else if (!this.handsWanted && this.hands) {
      this.hands = null;
      avatar.disableHandInput();
      // Sin cámara no llegan más fotogramas: ningún gesto puede quedar puesto.
      avatar.releaseGesture("L", { transition: 0.25 });
      avatar.releaseGesture("R", { transition: 0.25 });
    }
  }

  private readonly handleContextLost = (): void => {
    this.options.onContextLost?.();
  };

  private readonly handleContextRestored = (): void => {
    this.lastFrameAt = 0;
    this.monitor.reset(performance.now());
    this.options.onContextRestored?.();
  };
}

