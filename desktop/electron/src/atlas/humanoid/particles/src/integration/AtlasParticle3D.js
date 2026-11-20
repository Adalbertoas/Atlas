// ATLAS Fase 5F — adaptador "drop-in" para el dashboard: misma forma que Atlas3D (dashboard/js/atlas-3d.js):
//   const atlas = new AtlasParticle3D(container);  atlas.setState("thinking");  atlas.setAudioSamples(dataArray);  atlas.dispose();
// · Crea su lienzo dentro del contenedor, su cámara y su bucle; se adapta al tamaño con ResizeObserver.
// · Carga asíncrona: las llamadas a setState/setAudioSamples antes de terminar se guardan (sólo cuenta la última).
// · Igual que Atlas3D: setState lanza `atlasstatechange` en window y pone data-state en el contenedor.
// · Pausa al ocultarse la pestaña; pérdida y recuperación del contexto WebGL sin romper la página.
// · Si el equipo no tiene WebGL2 / texturas flotantes, no lanza: queda en modo "no disponible" (onerror) y la API
//   sigue respondiendo, para que app.js no tenga que cambiar.
import * as THREE from "../../vendor/three.module.js";
import { AtlasParticleAvatar } from "../AtlasParticleAvatar.js";

const STATE_ORDER = ["idle", "listening", "thinking", "executing", "speaking", "error"];

export class AtlasParticle3D {
  /**
   * @param {HTMLElement} container
   * @param {{glbUrl?: string, dataUrl?: string, quality?: "LOW"|"MEDIUM"|"HIGH"|"auto", bloom?: string, camera?: object, onerror?: (e:Error)=>void, onready?: ()=>void}} [o]
   */
  constructor(container, { glbUrl = "/assets/atlas/ATLAS_humanoid_v004.glb", dataUrl = "/assets/atlas/atlas_v004_particles", quality = "auto", bloom = "auto",
    camera = { fov: 30, position: [0, 1.25, 4.2], target: [0, 1.0, 0] }, onerror = null, onready = null } = {}) {
    this.container = container; this.state = "idle"; this.currentState = "idle"; this.available = null; this.avatar = null;
    this._pendingState = null; this._pendingSamples = null; this._raf = null; this._disposed = false; this._lost = false;
    this.setState = this.setState.bind(this); this.setAudioSamples = this.setAudioSamples.bind(this);
    this.canvas = document.createElement("canvas");
    Object.assign(this.canvas.style, { width: "100%", height: "100%", display: "block" });
    container.appendChild(this.canvas);
    this.camera = new THREE.PerspectiveCamera(camera.fov, 1, 0.05, 50);
    this.camera.position.fromArray(camera.position); this.camera.lookAt(new THREE.Vector3().fromArray(camera.target));
    this.scene = new THREE.Scene();
    this.contextLosses = 0; this.contextRestores = 0;
    const q = quality === "auto" ? AtlasParticle3D.suggestQuality() : quality;
    this.ready = AtlasParticleAvatar.create({ canvas: this.canvas, glbUrl, dataUrl, quality: q, bloom })
      .then(avatar => {
        if (this._disposed) { avatar.dispose(); return; }
        this.avatar = avatar; this.available = true;
        this.scene.add(avatar.object3D);
        this._onLost = e => { e.preventDefault(); this._lost = true; this.contextLosses++; cancelAnimationFrame(this._raf); };
        this._onRestored = () => { this._lost = false; this.contextRestores++; this._clock.getDelta(); this._loop(); };
        this.canvas.addEventListener("webglcontextlost", this._onLost);
        this.canvas.addEventListener("webglcontextrestored", this._onRestored);
        this._ro = new ResizeObserver(() => this._resize()); this._ro.observe(container); this._resize();
        this._onVis = () => { cancelAnimationFrame(this._raf); if (!document.hidden && !this._lost) { this._clock.getDelta(); this._loop(); } };
        document.addEventListener("visibilitychange", this._onVis);
        if (this._pendingState) avatar.setState(this._pendingState, { source: "dashboard" });
        if (this._pendingSamples) avatar.setAudioSamples(this._pendingSamples);
        this._clock = new THREE.Clock(); this._loop();
        onready?.();
      })
      .catch(err => { this.available = false; this.error = err; console.warn("[ATLAS 3D] humanoide de partículas no disponible:", err.message); onerror?.(err); });
  }

  /** LOW en equipos con poca memoria (mismo criterio que el LOD de Atlas3D), MEDIUM en el resto. */
  static suggestQuality() { return typeof navigator !== "undefined" && typeof navigator.deviceMemory === "number" && navigator.deviceMemory <= 4 ? "LOW" : "MEDIUM"; }

  setState(state) {
    const safe = STATE_ORDER.includes(state) ? state : "idle";
    this.state = this.currentState = safe;
    this.container?.setAttribute("data-state", safe);
    window.dispatchEvent(new CustomEvent("atlasstatechange", { detail: { state: safe } }));
    if (this.avatar) this.avatar.setState(safe, { source: "dashboard" }); else this._pendingState = safe;
  }

  setAudioSamples(samples) {
    if (!samples?.length) return;
    if (this.avatar) this.avatar.setAudioSamples(samples); else this._pendingSamples = Uint8Array.from(samples);
  }

  _resize() {
    if (!this.avatar) return;
    const w = Math.max(1, this.container.clientWidth), h = Math.max(1, this.container.clientHeight);
    this.avatar.engine.renderer.setSize(w, h, false);
    this.camera.aspect = w / h; this.camera.updateProjectionMatrix();
  }

  _loop() {
    if (this._disposed || this._lost || !this.avatar) return;
    cancelAnimationFrame(this._raf);
    this._raf = requestAnimationFrame(() => this._loop());
    const dt = Math.min(this._clock.getDelta(), 0.1);
    this.avatar.update(dt);
    this.avatar.render(this.scene, this.camera);
  }

  dispose() {
    this._disposed = true;
    cancelAnimationFrame(this._raf);
    this._ro?.disconnect();
    if (this._onVis) document.removeEventListener("visibilitychange", this._onVis);
    if (this._onLost) { this.canvas.removeEventListener("webglcontextlost", this._onLost); this.canvas.removeEventListener("webglcontextrestored", this._onRestored); }
    this.avatar?.dispose(); this.avatar = null;
    this.canvas.remove();
  }
}
