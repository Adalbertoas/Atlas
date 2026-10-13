// Worker de inferencia: MediaPipe corre aquí para no bloquear el hilo que
// renderiza el núcleo. Recibe fotogramas como ImageBitmap (transferidos, sin
// copia), los procesa y los cierra; devuelve solo coordenadas.

import { FilesetResolver, HandLandmarker } from "@mediapipe/tasks-vision";

export type HandWorkerRequest =
  | { type: "init"; assetBase: string; delegates: ("GPU" | "CPU")[] }
  | { type: "frame"; bitmap: ImageBitmap; timestamp: number };

export type HandWorkerResponse =
  | { type: "ready"; delegate: "GPU" | "CPU" }
  | { type: "failed"; message: string }
  | { type: "result"; timestamp: number; inferenceMs: number; hands: { landmarks: { x: number; y: number; z: number }[]; handedness: string | null }[] }
  | { type: "frame-error"; message: string };

const scope = self as unknown as { postMessage(message: HandWorkerResponse): void; onmessage: ((event: MessageEvent<HandWorkerRequest>) => void) | null };
let landmarker: HandLandmarker | null = null;

async function init(assetBase: string, delegates: ("GPU" | "CPU")[]): Promise<void> {
  // `true`: variante del cargador WASM para workers de tipo módulo.
  const fileset = await FilesetResolver.forVisionTasks(`${assetBase}/wasm`, true);
  let lastError: unknown = null;
  for (const delegate of delegates) {
    try {
      landmarker = await HandLandmarker.createFromOptions(fileset, {
        baseOptions: { modelAssetPath: `${assetBase}/hand_landmarker.task`, delegate },
        runningMode: "VIDEO",
        numHands: 2,
        minHandDetectionConfidence: 0.5,
        minHandPresenceConfidence: 0.5,
        minTrackingConfidence: 0.5,
      });
      scope.postMessage({ type: "ready", delegate });
      return;
    } catch (error) {
      lastError = error;
    }
  }
  throw lastError ?? new Error("Sin delegados disponibles.");
}

scope.onmessage = (event) => {
  const request = event.data;
  if (request.type === "init") {
    init(request.assetBase, request.delegates).catch((error) => scope.postMessage({ type: "failed", message: error instanceof Error ? error.message : String(error) }));
    return;
  }
  const { bitmap, timestamp } = request;
  try {
    if (!landmarker) throw new Error("Modelo no inicializado.");
    const started = performance.now();
    const result = landmarker.detectForVideo(bitmap, timestamp);
    scope.postMessage({
      type: "result",
      timestamp,
      inferenceMs: performance.now() - started,
      hands: result.landmarks.map((landmarks, index) => ({
        landmarks: landmarks.map((point) => ({ x: point.x, y: point.y, z: point.z })),
        handedness: result.handedness?.[index]?.[0]?.categoryName ?? null,
      })),
    });
  } catch (error) {
    scope.postMessage({ type: "frame-error", message: error instanceof Error ? error.message : String(error) });
  } finally {
    bitmap.close();
  }
};
