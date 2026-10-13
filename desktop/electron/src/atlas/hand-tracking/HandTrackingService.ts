// Cámara + MediaPipe Hand Landmarker. Los fotogramas se procesan en esta
// máquina y se descartan: nunca se guardan ni salen de ella. Lo único que
// produce el servicio son coordenadas de landmarks.
//
// La inferencia corre en un worker para no bloquear el hilo que renderiza el
// núcleo. Si el worker no puede arrancar se usa el hilo principal.

import type { HandWorkerRequest, HandWorkerResponse } from "./handWorker.ts";
import type { HandFrame, TrackedHand } from "./types.ts";

export type HandTrackingStatus = "off" | "starting" | "active" | "error";
export type InferenceDelegate = "GPU" | "CPU";

export type HandTrackingOptions = {
  /** Carpeta con `wasm/` y `hand_landmarker.task` (recursos locales, sin CDN). */
  assetBase: string;
  /** Inferencias por segundo como máximo; independiente de la tasa de render. */
  inferenceFps: number;
  /** Orden de preferencia; se usa el primero que consiga inicializarse. */
  delegates?: InferenceDelegate[];
  onFrame: (frame: HandFrame, inferenceMs: number) => void;
  onStatus: (status: HandTrackingStatus, error?: string) => void;
};

type RawHand = { landmarks: { x: number; y: number; z: number }[]; handedness: string | null };
type Detection = { hands: RawHand[]; inferenceMs: number };

/** Dónde corre el modelo. `detect` no se llama de nuevo hasta que resuelve. */
type InferenceEngine = {
  readonly description: string;
  detect(video: HTMLVideoElement, timestamp: number): Promise<Detection>;
  close(): void;
};

const MAX_CONSECUTIVE_FAILURES = 15;
// CPU primero: en una gráfica integrada la inferencia por GPU compite con el
// render del núcleo (medido en Intel UHD 630: 55 FPS con GPU frente a 60 con CPU).
const DEFAULT_DELEGATES: InferenceDelegate[] = ["CPU", "GPU"];

function cameraErrorMessage(error: unknown): string {
  const name = error instanceof DOMException ? error.name : "";
  if (name === "NotAllowedError" || name === "SecurityError") return "Permiso de camara denegado.";
  if (name === "NotFoundError" || name === "OverconstrainedError") return "No se encontro ninguna camara.";
  if (name === "NotReadableError" || name === "AbortError") return "La camara esta en uso por otra aplicacion o no responde.";
  return `No se pudo abrir la camara: ${error instanceof Error ? error.message : String(error)}`;
}

function createWorkerEngine(assetBase: string, delegates: InferenceDelegate[]): Promise<InferenceEngine> {
  return new Promise((resolve, reject) => {
    const worker = new Worker(new URL("./handWorker.ts", import.meta.url), { type: "module" });
    const send = (message: HandWorkerRequest, transfer: Transferable[] = []) => worker.postMessage(message, transfer);
    let pending: { resolve: (detection: Detection) => void; reject: (error: Error) => void } | null = null;
    const abort = (message: string) => {
      worker.terminate();
      pending?.reject(new Error(message));
      pending = null;
      reject(new Error(message));
    };
    worker.onerror = (event) => abort(event.message || "El worker de manos fallo.");
    worker.onmessage = (event: MessageEvent<HandWorkerResponse>) => {
      const message = event.data;
      if (message.type === "failed") abort(message.message);
      else if (message.type === "ready") {
        resolve({
          description: `worker/${message.delegate}`,
          async detect(video, timestamp) {
            // El fotograma viaja transferido: sin copia y sin tocar el disco.
            const bitmap = await createImageBitmap(video);
            return new Promise<Detection>((resolveDetection, rejectDetection) => {
              pending = { resolve: resolveDetection, reject: rejectDetection };
              send({ type: "frame", bitmap, timestamp }, [bitmap]);
            });
          },
          close() {
            worker.terminate();
            pending?.reject(new Error("Seguimiento detenido."));
            pending = null;
          },
        });
      } else if (message.type === "result") {
        pending?.resolve({ hands: message.hands, inferenceMs: message.inferenceMs });
        pending = null;
      } else {
        pending?.reject(new Error(message.message));
        pending = null;
      }
    };
    send({ type: "init", assetBase, delegates });
  });
}

async function createMainThreadEngine(assetBase: string, delegates: InferenceDelegate[]): Promise<InferenceEngine> {
  const { FilesetResolver, HandLandmarker } = await import("@mediapipe/tasks-vision");
  const fileset = await FilesetResolver.forVisionTasks(`${assetBase}/wasm`);
  let lastError: unknown = null;
  for (const delegate of delegates) {
    try {
      const landmarker = await HandLandmarker.createFromOptions(fileset, {
        baseOptions: { modelAssetPath: `${assetBase}/hand_landmarker.task`, delegate },
        runningMode: "VIDEO",
        numHands: 2,
        minHandDetectionConfidence: 0.5,
        minHandPresenceConfidence: 0.5,
        minTrackingConfidence: 0.5,
      });
      return {
        description: `main/${delegate}`,
        async detect(video, timestamp) {
          const started = performance.now();
          const result = landmarker.detectForVideo(video, timestamp);
          return {
            inferenceMs: performance.now() - started,
            hands: result.landmarks.map((landmarks, index) => ({ landmarks, handedness: result.handedness?.[index]?.[0]?.categoryName ?? null })),
          };
        },
        close: () => landmarker.close(),
      };
    } catch (error) {
      lastError = error;
    }
  }
  throw lastError ?? new Error("Sin delegados disponibles.");
}

export class HandTrackingService {
  private readonly options: HandTrackingOptions;
  private engine: InferenceEngine | null = null;
  private loading: Promise<InferenceEngine> | null = null;
  private stream: MediaStream | null = null;
  private video: HTMLVideoElement | null = null;
  private timer = 0;
  private session = 0;
  private lastVideoTime = -1;
  private lastTimestamp = 0;
  private failures = 0;
  private status: HandTrackingStatus = "off";

  constructor(options: HandTrackingOptions) {
    this.options = options;
  }

  /** Elemento de vídeo en uso; solo para la vista de depuración opcional. */
  get videoElement(): HTMLVideoElement | null {
    return this.video;
  }

  /** "worker/GPU", "main/CPU"…; null hasta que el modelo está cargado. */
  get engineDescription(): string | null {
    return this.engine?.description ?? null;
  }

  /** Carga WASM y modelo sin tocar la cámara. */
  loadModel(): Promise<InferenceEngine> {
    if (this.engine) return Promise.resolve(this.engine);
    this.loading ??= this.createEngine().then(
      (engine) => {
        this.engine = engine;
        this.loading = null;
        return engine;
      },
      (error) => {
        this.loading = null;
        throw error;
      },
    );
    return this.loading;
  }

  async start(): Promise<void> {
    if (this.status === "starting" || this.status === "active") return;
    const session = ++this.session;
    this.setStatus("starting");

    let stream: MediaStream;
    try {
      stream = await navigator.mediaDevices.getUserMedia({ video: { width: { ideal: 640 }, height: { ideal: 480 }, facingMode: "user" }, audio: false });
    } catch (error) {
      if (session === this.session) this.setStatus("error", cameraErrorMessage(error));
      return;
    }
    // Si el usuario la apagó mientras se pedía el permiso, se suelta de inmediato.
    if (session !== this.session) {
      stream.getTracks().forEach((track) => track.stop());
      return;
    }
    this.stream = stream;
    stream.getVideoTracks()[0]?.addEventListener("ended", () => {
      if (session === this.session) this.fail("La camara se desconecto.");
    });

    try {
      const video = document.createElement("video");
      video.muted = true;
      video.playsInline = true;
      video.srcObject = stream;
      this.video = video;
      await video.play();
      await this.loadModel();
    } catch (error) {
      if (session === this.session) this.fail(`No se pudo iniciar el seguimiento de manos: ${error instanceof Error ? error.message : String(error)}`);
      return;
    }
    if (session !== this.session) return;

    this.failures = 0;
    this.lastVideoTime = -1;
    this.setStatus("active");
    void this.loop(session);
  }

  /** Apaga la cámara de inmediato. El modelo queda en memoria para reactivar rápido. */
  stop(): void {
    this.session += 1;
    this.releaseCamera();
    if (this.status !== "off") this.setStatus("off");
  }

  dispose(): void {
    this.stop();
    this.engine?.close();
    this.engine = null;
  }

  private fail(message: string): void {
    this.session += 1;
    this.releaseCamera();
    this.setStatus("error", message);
  }

  private releaseCamera(): void {
    window.clearTimeout(this.timer);
    this.timer = 0;
    this.stream?.getTracks().forEach((track) => track.stop());
    this.stream = null;
    if (this.video) {
      this.video.pause();
      this.video.srcObject = null;
      this.video = null;
    }
  }

  private setStatus(status: HandTrackingStatus, error?: string): void {
    this.status = status;
    this.options.onStatus(status, error);
  }

  private async createEngine(): Promise<InferenceEngine> {
    const base = this.options.assetBase.replace(/\/$/, "");
    const delegates = this.options.delegates ?? DEFAULT_DELEGATES;
    try {
      return await createWorkerEngine(base, delegates);
    } catch (error) {
      console.warn("[neural-core] Worker de manos no disponible; se usa el hilo principal.", error);
      return createMainThreadEngine(base, delegates);
    }
  }

  private async loop(session: number): Promise<void> {
    if (session !== this.session) return;
    const started = performance.now();
    await this.infer(started, session);
    if (session !== this.session) return;
    // Temporizador propio en vez de requestAnimationFrame: la inferencia va a
    // su ritmo y no compite con cada fotograma del render.
    const interval = 1000 / this.options.inferenceFps;
    this.timer = window.setTimeout(() => void this.loop(session), Math.max(0, interval - (performance.now() - started)));
  }

  private async infer(now: number, session: number): Promise<void> {
    const video = this.video;
    const engine = this.engine;
    if (!video || !engine || video.readyState < 2 || document.hidden) return;
    // Sin fotograma nuevo no hay nada que inferir.
    if (video.currentTime === this.lastVideoTime) return;
    this.lastVideoTime = video.currentTime;
    // MediaPipe exige marcas de tiempo estrictamente crecientes.
    const timestamp = Math.max(now, this.lastTimestamp + 1);
    this.lastTimestamp = timestamp;

    try {
      const detection = await engine.detect(video, timestamp);
      if (session !== this.session) return;
      const hands: TrackedHand[] = detection.hands.map((hand) => ({
        // Vista de espejo: mover la mano a la derecha mueve el núcleo a la derecha.
        landmarks: hand.landmarks.map((point) => ({ x: 1 - point.x, y: point.y, z: point.z })),
        handedness: hand.handedness,
      }));
      this.failures = 0;
      this.options.onFrame({ timestamp, hands }, detection.inferenceMs);
    } catch (error) {
      if (session !== this.session) return;
      this.failures += 1;
      if (this.failures >= MAX_CONSECUTIVE_FAILURES) this.fail(`El seguimiento de manos dejo de responder: ${error instanceof Error ? error.message : String(error)}`);
    }
  }
}
