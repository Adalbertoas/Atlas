import * as THREE from "three";
import { ParticleAnimator, type CoreInputs } from "./ParticleAnimator.ts";
import { createBloomPipeline, Halo, type BloomPipeline } from "./ParticleEffects.ts";
import { createParticleGeometry } from "./ParticleGeometry.ts";
import { applyFrame, createParticleMaterial } from "./ParticleMaterial.ts";
import { QUALITY_PROFILES, type QualityLevel } from "./ParticlePresets.ts";
import { PerformanceMonitor } from "./PerformanceMonitor.ts";

export type CoreStats = { fps: number; renderMs: number; particles: number; quality: QualityLevel; bloom: boolean };

export type ParticleCoreOptions = {
  canvas: HTMLCanvasElement;
  quality: QualityLevel;
  bloom: boolean;
  /** Se llama una vez por fotograma; el núcleo no sabe de dónde salen los datos. */
  provideInputs: (dt: number, now: number) => CoreInputs;
  onStats?: (stats: CoreStats) => void;
  onPerformanceDegraded?: (quality: QualityLevel) => void;
  onContextLost?: () => void;
  onContextRestored?: () => void;
  onError?: (error: unknown) => void;
};

const FOV = 42;
const CAMERA_DISTANCE = 4;
const STATS_INTERVAL_MS = 500;
const VISIBLE_HEIGHT = 2 * CAMERA_DISTANCE * Math.tan((FOV * Math.PI) / 360);
// El núcleo se centra al 42 % de la altura, igual que el planeta y las órbitas
// del fondo: así asoma por encima del panel de chat en la disposición inicial.
const VERTICAL_CENTER = 0.42;

/** Encuadre de la escena en z = 0, para quien necesite situar puntos sobre ella. */
export const CORE_VIEW = { halfHeight: VISIBLE_HEIGHT / 2, centerY: -(0.5 - VERTICAL_CENTER) * VISIBLE_HEIGHT } as const;

/** Motor de partículas. Depende solo de Three.js: no conoce React, el asistente,
    la cámara ni el audio. */
export class ParticleCore {
  private readonly options: ParticleCoreOptions;
  private readonly canvas: HTMLCanvasElement;
  private readonly renderer: THREE.WebGLRenderer;
  private readonly scene = new THREE.Scene();
  private readonly camera = new THREE.PerspectiveCamera(FOV, 1, 0.1, 50);
  private readonly halo = new Halo();
  private readonly monitor = new PerformanceMonitor();
  private readonly resizeObserver: ResizeObserver;
  private points: THREE.Points<THREE.BufferGeometry, THREE.ShaderMaterial> | null = null;
  private readonly animator: ParticleAnimator;
  private bloom: BloomPipeline | null = null;
  private bloomWanted: boolean;
  private bloomRequest = 0;
  private quality: QualityLevel;
  private rafId = 0;
  private running = false;
  private contextLost = false;
  private disposed = false;
  private lastFrame = 0;
  private lastStats = 0;
  private renderMs = 0;

  /** Lanza si WebGL no está disponible; quien lo monte decide el plan B. */
  constructor(options: ParticleCoreOptions) {
    this.options = options;
    this.canvas = options.canvas;
    this.quality = options.quality;
    this.bloomWanted = options.bloom;
    this.animator = new ParticleAnimator(QUALITY_PROFILES[options.quality].pointScale);

    this.renderer = new THREE.WebGLRenderer({ canvas: this.canvas, antialias: false, alpha: false, powerPreference: "high-performance", stencil: false, depth: false });
    // Fondo negro opaco: la capa se compone sobre la interfaz con
    // mix-blend-mode: screen, donde el negro equivale a transparente.
    this.renderer.setClearColor(0x000000, 1);
    this.camera.position.set(0, CORE_VIEW.centerY, CAMERA_DISTANCE);
    this.scene.add(this.halo.mesh);
    this.buildPoints();

    this.canvas.addEventListener("webglcontextlost", this.handleContextLost);
    this.canvas.addEventListener("webglcontextrestored", this.handleContextRestored);
    document.addEventListener("visibilitychange", this.handleVisibility);
    this.resizeObserver = new ResizeObserver(() => this.resize());
    this.resizeObserver.observe(this.canvas.parentElement ?? this.canvas);
    this.resize();
    void this.syncBloom();
  }

  get rendererName(): string | null {
    try {
      const gl = this.renderer.getContext();
      const info = gl.getExtension("WEBGL_debug_renderer_info");
      return info ? String(gl.getParameter(info.UNMASKED_RENDERER_WEBGL)) : null;
    } catch {
      return null;
    }
  }

  start(): void {
    if (this.running || this.disposed) return;
    this.running = true;
    this.lastFrame = 0;
    this.monitor.reset(performance.now());
    this.schedule();
  }

  stop(): void {
    this.running = false;
    cancelAnimationFrame(this.rafId);
    this.rafId = 0;
  }

  setQuality(quality: QualityLevel): void {
    if (quality === this.quality || this.disposed) return;
    this.quality = quality;
    // Se conserva el animador (y con él el estado de la animación): el cambio
    // de calidad no reinicia el movimiento.
    this.animator.setPointScale(QUALITY_PROFILES[quality].pointScale);
    this.buildPoints();
    this.resize();
    this.monitor.reset(performance.now());
    void this.syncBloom();
  }

  setBloom(enabled: boolean): void {
    if (enabled === this.bloomWanted) return;
    this.bloomWanted = enabled;
    void this.syncBloom();
  }

  triggerExplosion(): void {
    this.animator.triggerExplosion();
  }

  reconstruct(): void {
    this.animator.reconstruct();
  }

  triggerPulse(): void {
    this.animator.triggerPulse();
  }

  dispose(): void {
    if (this.disposed) return;
    this.disposed = true;
    this.stop();
    this.resizeObserver.disconnect();
    document.removeEventListener("visibilitychange", this.handleVisibility);
    this.canvas.removeEventListener("webglcontextlost", this.handleContextLost);
    this.canvas.removeEventListener("webglcontextrestored", this.handleContextRestored);
    this.disposePoints();
    this.halo.dispose();
    this.bloom?.dispose();
    this.bloom = null;
    this.renderer.dispose();
    // Libera la memoria de GPU de inmediato en vez de esperar al recolector.
    this.renderer.forceContextLoss();
  }

  private buildPoints(): void {
    this.disposePoints();
    const profile = QUALITY_PROFILES[this.quality];
    this.points = new THREE.Points(createParticleGeometry(profile.particleCount), createParticleMaterial(profile));
    this.points.frustumCulled = false;
    this.scene.add(this.points);
  }

  private disposePoints(): void {
    if (!this.points) return;
    this.scene.remove(this.points);
    this.points.geometry.dispose();
    this.points.material.dispose();
    this.points = null;
  }

  private async syncBloom(): Promise<void> {
    const request = ++this.bloomRequest;
    const wanted = this.bloomWanted && QUALITY_PROFILES[this.quality].bloomAllowed;
    if (!wanted) {
      this.bloom?.dispose();
      this.bloom = null;
      return;
    }
    if (this.bloom) return;
    try {
      const pipeline = await createBloomPipeline(this.renderer, this.scene, this.camera);
      if (request !== this.bloomRequest || this.disposed) {
        pipeline.dispose();
        return;
      }
      this.bloom = pipeline;
      this.resize();
    } catch (error) {
      // Sin bloom el núcleo sigue viéndose bien gracias al halo.
      console.warn("[neural-core] Bloom no disponible:", error);
      this.bloom = null;
    }
  }

  private resize(): void {
    if (this.disposed) return;
    const host = this.canvas.parentElement ?? this.canvas;
    const width = Math.max(1, host.clientWidth);
    const height = Math.max(1, host.clientHeight);
    const pixelRatio = Math.min(window.devicePixelRatio || 1, QUALITY_PROFILES[this.quality].maxPixelRatio);
    this.renderer.setPixelRatio(pixelRatio);
    this.renderer.setSize(width, height, false);
    this.camera.aspect = width / height;
    this.camera.updateProjectionMatrix();
    this.bloom?.setSize(width, height, pixelRatio);
    if (this.points) {
      // Convierte tamaños en unidades de escena a píxeles del framebuffer.
      this.points.material.uniforms.uScale.value = (height * pixelRatio) / (2 * Math.tan(THREE.MathUtils.degToRad(FOV) / 2));
    }
  }

  private schedule(): void {
    if (!this.running || this.contextLost || document.hidden) return;
    this.rafId = requestAnimationFrame(this.renderFrame);
  }

  private readonly renderFrame = (now: number): void => {
    if (!this.running || this.disposed) return;
    try {
      this.drawFrame(now);
    } catch (error) {
      // Un fallo de render detiene el núcleo, no la aplicación.
      this.stop();
      this.options.onError?.(error);
      return;
    }
    this.schedule();
  };

  private drawFrame(now: number): void {
    const frameMs = this.lastFrame ? now - this.lastFrame : 16.7;
    this.lastFrame = now;
    const dt = Math.min(frameMs / 1000, 0.1);

    const frame = this.animator.step(dt, this.options.provideInputs(dt, now));
    if (this.points) applyFrame(this.points.material, frame);
    this.halo.update(frame.colorA, frame.halo);

    const renderStart = performance.now();
    if (this.bloom) this.bloom.render();
    else this.renderer.render(this.scene, this.camera);
    this.renderMs += (performance.now() - renderStart - this.renderMs) * 0.1;

    if (this.monitor.sample(frameMs, now)) this.options.onPerformanceDegraded?.(this.quality);
    if (now - this.lastStats >= STATS_INTERVAL_MS) {
      this.lastStats = now;
      this.options.onStats?.({ fps: this.monitor.fps, renderMs: this.renderMs, particles: QUALITY_PROFILES[this.quality].particleCount, quality: this.quality, bloom: this.bloom !== null });
    }
  }

  private readonly handleVisibility = (): void => {
    if (document.hidden) {
      cancelAnimationFrame(this.rafId);
      return;
    }
    this.lastFrame = 0;
    this.monitor.reset(performance.now());
    this.schedule();
  };

  private readonly handleContextLost = (event: Event): void => {
    // preventDefault es lo que permite que el navegador restaure el contexto.
    event.preventDefault();
    this.contextLost = true;
    cancelAnimationFrame(this.rafId);
    this.options.onContextLost?.();
  };

  private readonly handleContextRestored = (): void => {
    this.contextLost = false;
    this.lastFrame = 0;
    this.monitor.reset(performance.now());
    this.options.onContextRestored?.();
    this.schedule();
  };
}
