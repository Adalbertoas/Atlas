// Tipos para usar desde TypeScript el adaptador del laboratorio (AtlasParticle3D.js, copiado sin cambios).
// Solo declara lo que usa la aplicación de escritorio.

export type HumanoidQuality = "LOW" | "MEDIUM" | "HIGH";
export type HumanoidBloom = "auto" | "on" | "off";

export type HandLandmarkerResult = {
  landmarks: { x: number; y: number; z: number }[][];
  handedness: { categoryName: string; score: number }[][];
};

/** Proveedor de manos propio: el humanoide no abre otra cámara, recibe los landmarks de la aplicación. */
export type HandProvider = {
  name?: string;
  status?: string;
  onResult?: ((result: HandLandmarkerResult, tMs: number) => void) | null;
  start(): Promise<boolean> | boolean;
  dispose?(): void;
};

export interface HumanoidAvatar {
  engine: { renderer: { setClearColor(color: number, alpha: number): void; setPixelRatio(ratio: number): void; getPixelRatio(): number; getContext(): WebGLRenderingContext | WebGL2RenderingContext; info: { render: { calls: number } } }; quality: HumanoidQuality; count: number; bloomOn: boolean };
  perf: { fps: number; frameMs: number };
  state: string;
  update(dt: number): void;
  render(scene: unknown, camera: unknown): void;
  setQuality(quality: HumanoidQuality): void;
  setBloom(mode: HumanoidBloom): void;
  setCoreVisible(visible: boolean): void;
  enableHandInput(options: { provider: HandProvider }): Promise<{ ok: boolean; status: string; message?: string }>;
  disableHandInput(): void;
  releaseGesture(side: "L" | "R", options?: { transition?: number }): void;
}

export type AtlasParticle3DOptions = {
  glbUrl?: string;
  dataUrl?: string;
  quality?: HumanoidQuality | "auto";
  bloom?: HumanoidBloom;
  camera?: { fov: number; position: [number, number, number]; target: [number, number, number] };
  onerror?: ((error: Error) => void) | null;
  onready?: (() => void) | null;
};

export class AtlasParticle3D {
  constructor(container: HTMLElement, options?: AtlasParticle3DOptions);
  readonly canvas: HTMLCanvasElement;
  readonly ready: Promise<void>;
  available: boolean | null;
  avatar: HumanoidAvatar | null;
  error?: Error;
  state: string;
  contextLosses: number;
  contextRestores: number;
  static suggestQuality(): HumanoidQuality;
  setState(state: string): void;
  setAudioSamples(samples: Uint8Array): void;
  dispose(): void;
}
