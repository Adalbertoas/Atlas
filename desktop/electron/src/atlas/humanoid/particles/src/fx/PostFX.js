// ATLAS Fase 5E — bloom opcional (UnrealBloomPass de Three.js r164, copiado de examples/jsm sin cambios salvo la ruta
// del import). Se renderiza la escena del motor en un búfer de media precisión (HDR), se aplica el bloom y se copia a
// pantalla SIN conversión de color: los shaders del humanoide y del núcleo ya escriben el color final, así que con y sin
// bloom los colores base son los mismos.
import * as THREE from "../../vendor/three.module.js";
import { EffectComposer } from "../../vendor/postprocessing/EffectComposer.js";
import { Pass } from "../../vendor/postprocessing/Pass.js";
import { ShaderPass } from "../../vendor/postprocessing/ShaderPass.js";
import { UnrealBloomPass } from "../../vendor/postprocessing/UnrealBloomPass.js";
import { CopyShader } from "../../vendor/shaders/CopyShader.js";

class EngineScenePass extends Pass {
  constructor(draw) { super(); this.draw = draw; this.needsSwap = false; }
  render(renderer, writeBuffer, readBuffer) {
    renderer.setRenderTarget(this.renderToScreen ? null : readBuffer);
    renderer.clear();
    this.draw();
  }
}

export class PostFX {
  /** @param {THREE.WebGLRenderer} renderer */
  constructor(renderer, { strength = 0.6, radius = 0.5, threshold = 0.55, maxValue = 2.0, resolutionScale = 0.5, enabled = true } = {}) {
    this.resolutionScale = resolutionScale;   // el bloom se calcula a media resolución (es un desenfoque: no se nota y cuesta ~4× menos)
    this.renderer = renderer;
    this.enabled = enabled;
    this.size = new THREE.Vector2();
    renderer.getDrawingBufferSize(this.size);
    this.composer = new EffectComposer(renderer);
    this.composer.setPixelRatio(1);               // el tamaño ya viene en píxeles físicos
    this.composer.setSize(this.size.x, this.size.y);
    this.scenePass = new EngineScenePass(() => this._draw?.());
    // límite de brillo antes del bloom: donde se acumulan muchas capas aditivas (ondas, chispas) el HDR crece sin
    // límite y el bloom lo convertiría en una mancha; con el tope el resplandor queda proporcionado
    this.clamp = new ShaderPass({ uniforms: { tDiffuse: { value: null }, uMax: { value: maxValue } },
      vertexShader: CopyShader.vertexShader,
      fragmentShader: "uniform sampler2D tDiffuse; uniform float uMax; varying vec2 vUv; void main(){ vec4 c = texture2D(tDiffuse, vUv); gl_FragColor = vec4(min(c.rgb, vec3(uMax)), 1.0); }" });
    this.bloom = new UnrealBloomPass(new THREE.Vector2(this.size.x * resolutionScale, this.size.y * resolutionScale), strength, radius, threshold);
    this.copy = new ShaderPass(CopyShader);
    this.composer.addPass(this.scenePass); this.composer.addPass(this.clamp); this.composer.addPass(this.bloom); this.composer.addPass(this.copy);
    this.bloom.setSize(this.size.x * resolutionScale, this.size.y * resolutionScale);   // addPass lo había puesto a resolución completa
  }
  set({ strength, radius, threshold, enabled } = {}) {
    if (strength !== undefined) this.bloom.strength = strength;
    if (radius !== undefined) this.bloom.radius = radius;
    if (threshold !== undefined) this.bloom.threshold = threshold;
    if (enabled !== undefined) this.enabled = enabled;
  }
  /** draw: función que dibuja la escena con el renderer (el render target ya está fijado). */
  render(draw) {
    const s = this.renderer.getDrawingBufferSize(this._tmp ||= new THREE.Vector2());
    if (s.x !== this.size.x || s.y !== this.size.y) { this.size.copy(s); this.composer.setSize(s.x, s.y); this.bloom.setSize(s.x * this.resolutionScale, s.y * this.resolutionScale); }
    this._draw = draw;
    const info = this.renderer.info, ar = info.autoReset;     // contar las llamadas de todas las pasadas del frame
    info.autoReset = false; info.reset();
    this.composer.render();
    info.autoReset = ar;
  }
  /** Memoria de GPU estimada (bytes) de los búferes del postprocesado (RGBA media precisión = 8 B/píxel). */
  memoryBytes() {
    const { x, y } = this.size; let b = 2 * x * y * 8;            // dos búferes del compositor a resolución completa
    let rx = Math.round(x * this.resolutionScale / 2), ry = Math.round(y * this.resolutionScale / 2);
    b += rx * ry * 8;                                              // paso de brillo
    for (let i = 0; i < 5; i++) { b += 2 * rx * ry * 8; rx = Math.round(rx / 2); ry = Math.round(ry / 2); }   // 5 niveles × (horizontal + vertical)
    return b;
  }
  dispose() { this.bloom.dispose(); this.copy.material?.dispose(); this.clamp.material?.dispose(); this.composer.renderTarget1.dispose(); this.composer.renderTarget2.dispose(); this.composer.dispose?.(); }
}
