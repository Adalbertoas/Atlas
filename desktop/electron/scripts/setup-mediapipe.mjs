// Prepara los recursos locales de MediaPipe en public/mediapipe/ para que el
// seguimiento de manos funcione sin CDN en tiempo de ejecución:
//   - wasm/                 copiado desde node_modules/@mediapipe/tasks-vision
//   - hand_landmarker.task  modelo oficial de Google (se descarga una sola vez)
//
//   node scripts/setup-mediapipe.mjs            copia el WASM y descarga el modelo si falta
//   node scripts/setup-mediapipe.mjs --offline  solo copia el WASM; avisa si falta el modelo
import { cp, mkdir, stat, writeFile } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const wasmSource = path.join(root, "node_modules", "@mediapipe", "tasks-vision", "wasm");
const target = path.join(root, "public", "mediapipe");
const modelPath = path.join(target, "hand_landmarker.task");
// Modelo Hand Landmarker (float16, versión 1) publicado por Google para MediaPipe Tasks.
const MODEL_URL = "https://storage.googleapis.com/mediapipe-models/hand_landmarker/hand_landmarker/float16/1/hand_landmarker.task";
const offline = process.argv.includes("--offline");

const exists = (file) => stat(file).then(() => true, () => false);

await mkdir(target, { recursive: true });

if (await exists(wasmSource)) {
  // Hacen falta las dos variantes: "_module_" para el worker de inferencia y la
  // clásica para el plan B en el hilo principal.
  await cp(wasmSource, path.join(target, "wasm"), { recursive: true });
  console.log("[mediapipe] WASM copiado a public/mediapipe/wasm");
} else {
  console.warn("[mediapipe] Falta @mediapipe/tasks-vision: ejecuta `npm install`.");
}

if (await exists(modelPath)) {
  console.log("[mediapipe] Modelo presente: public/mediapipe/hand_landmarker.task");
} else if (offline) {
  console.warn("[mediapipe] Falta el modelo de manos. El control gestual no funcionara hasta ejecutar `npm run setup:mediapipe`.");
} else {
  console.log(`[mediapipe] Descargando modelo desde ${MODEL_URL}`);
  const response = await fetch(MODEL_URL);
  if (!response.ok) throw new Error(`No se pudo descargar el modelo (HTTP ${response.status}).`);
  const bytes = Buffer.from(await response.arrayBuffer());
  await writeFile(modelPath, bytes);
  console.log(`[mediapipe] Modelo guardado (${(bytes.length / 1048576).toFixed(1)} MB).`);
}
