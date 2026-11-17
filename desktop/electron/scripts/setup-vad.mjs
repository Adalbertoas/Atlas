// Copia el runtime WASM de ONNX (onnxruntime-web) a public/vad/ort/ para que el
// detector de voz Silero funcione sin CDN en tiempo de ejecución. El modelo
// (public/vad/silero_vad_v6.onnx, 1,2 MB, MIT) ya está en el repositorio.
//
//   node scripts/setup-vad.mjs
import { copyFile, mkdir, stat } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const source = path.join(root, "node_modules", "onnxruntime-web", "dist");
const target = path.join(root, "public", "vad", "ort");
// Solo el backend WASM (sin WebGPU/WebGL): Silero es diminuto y corre en CPU.
const FILES = ["ort-wasm-simd-threaded.wasm", "ort-wasm-simd-threaded.mjs"];

const exists = (file) => stat(file).then(() => true, () => false);

if (!(await exists(source))) {
  console.warn("[vad] Falta onnxruntime-web: ejecuta `npm install`. La escucha usara el detector por volumen.");
} else {
  await mkdir(target, { recursive: true });
  for (const file of FILES) await copyFile(path.join(source, file), path.join(target, file));
  console.log("[vad] Runtime ONNX copiado a public/vad/ort");
}
