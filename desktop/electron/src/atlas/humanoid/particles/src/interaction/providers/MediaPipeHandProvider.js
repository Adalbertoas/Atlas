// ATLAS Fase 5D — proveedor de manos con MediaPipe Tasks Vision (HandLandmarker), igual que el dashboard de ATLAS:
// mismas URLs por defecto (único recurso de CDN del proyecto), mismas opciones (2 manos, umbrales 0.3, modo VIDEO,
// delegado GPU) y misma regla de privacidad: el vídeo nunca sale del navegador, sólo se usan los landmarks.
// No añade dependencias al proyecto: la librería se importa en tiempo de ejecución desde la URL configurada
// (se puede apuntar a una copia local con `visionUrl` / `modelUrl`).
// Sin permiso de cámara, sin red o sin WebGL para MediaPipe → estado "denied"/"error" y el humanoide sigue igual.

export const MEDIAPIPE_DEFAULTS = {
  visionUrl: "https://cdn.jsdelivr.net/npm/@mediapipe/tasks-vision@0.10.14",
  modelUrl: "https://storage.googleapis.com/mediapipe-models/hand_landmarker/hand_landmarker/float16/1/hand_landmarker.task",
};

export class MediaPipeHandProvider extends EventTarget {
  /**
   * @param {{onResult: (result: object, tMs: number) => void, visionUrl?: string, wasmUrl?: string, modelUrl?: string,
   *          delegate?: "GPU"|"CPU", maxFps?: number, source?: HTMLVideoElement|HTMLCanvasElement, video?: {width:number,height:number}}} o
   *  source: si se da, se analiza ese elemento (pruebas o un vídeo propio); si no, se abre la cámara frontal.
   */
  constructor({ onResult, visionUrl = MEDIAPIPE_DEFAULTS.visionUrl, wasmUrl, modelUrl = MEDIAPIPE_DEFAULTS.modelUrl, delegate = "GPU", maxFps = 30, source = null, video = { width: 640, height: 480 } } = {}) {
    super();
    Object.assign(this, { onResult, visionUrl, wasmUrl: wasmUrl || `${visionUrl}/wasm`, modelUrl, delegate, maxFps, source, videoSize: video });
    this.status = "stopped"; this.landmarker = null; this.stream = null; this.video = null; this.raf = null; this.lastTs = -1; this.lastRun = 0;
    this.stats = { frames: 0, detections: 0, lastMs: 0, avgMs: 0 };
    this.name = "MediaPipe";
  }

  _set(status, detail = {}) { this.status = status; if (detail.message) this.lastMessage = detail.message; this.dispatchEvent(new CustomEvent("status", { detail: { status, ...detail } })); }

  async load() {
    if (this.landmarker) return this.landmarker;
    this._set("loading");
    const { HandLandmarker, FilesetResolver } = await import(/* @vite-ignore */ `${this.visionUrl}/vision_bundle.mjs`);
    const vision = await FilesetResolver.forVisionTasks(this.wasmUrl);
    const opts = { baseOptions: { modelAssetPath: this.modelUrl, delegate: this.delegate }, numHands: 2, runningMode: "VIDEO",
      minHandDetectionConfidence: 0.3, minHandPresenceConfidence: 0.3, minTrackingConfidence: 0.3 };
    try { this.landmarker = await HandLandmarker.createFromOptions(vision, opts); }
    catch (err) {                                           // sin GPU para MediaPipe: se reintenta en CPU
      if (this.delegate !== "GPU") throw err;
      this.landmarker = await HandLandmarker.createFromOptions(vision, { ...opts, baseOptions: { ...opts.baseOptions, delegate: "CPU" } });
      this.delegate = "CPU";
    }
    return this.landmarker;
  }

  /** Abre la cámara (si no hay `source`), carga el modelo y empieza a detectar. Nunca lanza: informa por "status". */
  async start() {
    if (this.status === "running" || this.status === "starting") return true;
    this._set("starting");
    try {
      if (!this.source) {
        if (!navigator.mediaDevices?.getUserMedia) { this._set("unsupported", { message: "El navegador no permite usar la cámara (getUserMedia)." }); return false; }
        try { this.stream = await navigator.mediaDevices.getUserMedia({ video: { facingMode: "user", ...this.videoSize }, audio: false }); }
        catch (err) { this._set("denied", { message: `Sin acceso a la cámara: ${err.name || ""} ${err.message || ""}`.trim() }); return false; }
        this.video = Object.assign(document.createElement("video"), { muted: true, playsInline: true, autoplay: true });
        this.video.srcObject = this.stream;
        await this.video.play().catch(() => {});
      }
      await this.load();
    } catch (err) {
      this.stop();
      this._set("error", { message: `No se pudo cargar MediaPipe: ${err.message}` });
      return false;
    }
    this._set("running", { delegate: this.delegate });
    this._loop();
    return true;
  }

  /** Detecta en un frame concreto (también lo usan las pruebas). Devuelve el resultado de HandLandmarker. */
  detect(el = this.source || this.video, tMs = performance.now()) {
    if (!this.landmarker || !el) return null;
    if (el instanceof HTMLVideoElement && el.readyState < 2) return null;
    const ts = Math.max(tMs, this.lastTs + 1);             // MediaPipe exige marcas de tiempo crecientes
    this.lastTs = ts;
    const t0 = performance.now();
    const result = this.landmarker.detectForVideo(el, ts);
    const ms = performance.now() - t0;
    this.stats.frames++; this.stats.lastMs = ms; this.stats.avgMs += (ms - this.stats.avgMs) / Math.min(this.stats.frames, 60);
    if (result?.landmarks?.length) this.stats.detections++;
    return result;
  }

  _loop() {
    if (this.status !== "running") return;
    this.raf = requestAnimationFrame(() => this._loop());
    const now = performance.now();
    if (now - this.lastRun < 1000 / this.maxFps) return;
    this.lastRun = now;
    const result = this.detect(undefined, now);
    if (result) this.onResult?.(result, now);
  }

  stop() {
    cancelAnimationFrame(this.raf); this.raf = null;
    if (this.stream) { for (const t of this.stream.getTracks()) t.stop(); this.stream = null; }
    if (this.video) { this.video.srcObject = null; this.video = null; }
    if (this.status !== "denied" && this.status !== "error" && this.status !== "unsupported") this._set("stopped");
  }

  dispose() { this.stop(); this.landmarker?.close?.(); this.landmarker = null; }
}
