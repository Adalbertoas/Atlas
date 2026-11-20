// ATLAS Fase 5B — motor de partículas: pase de skinning en GPU + render de puntos.
// Puede crear su propio WebGLRenderer (laboratorio) o usar uno existente (futuro Atlas3D):
// en ese caso se añade `engine.object3D` a la escena del anfitrión y se llama a `engine.computeSkin()` antes de renderizar.
import * as THREE from "../../vendor/three.module.js";
import { skinVertexShader, skinFragmentShader } from "./shaders/skinning.glsl.js";
import { pointsVertexShader, pointsFragmentShader } from "./shaders/points.glsl.js";
import { PostFX } from "../fx/PostFX.js";

export const QUALITY = {
  LOW: { count: 16384, pointSize: 0.0075 },
  MEDIUM: { count: 65536, pointSize: 0.0048 },
  HIGH: { count: 131072, pointSize: 0.0036 },
};
// tamaño relativo por región: cabeza, torso, brazo, mano, pierna (las manos, más finas)
const REGION_SCALE = [0.95, 1.0, 1.0, 0.8, 1.05];

export class ParticleEngine {
  /**
   * @param {{model: import('../model/HumanoidParticleModel.js').HumanoidParticleModel, canvas?: HTMLCanvasElement,
   *          renderer?: THREE.WebGLRenderer, quality?: keyof QUALITY}} opts
   */
  constructor({ model, canvas, renderer, quality = "MEDIUM" }) {
    this.model = model;
    this.ownsRenderer = !renderer;
    this.renderer = renderer || new THREE.WebGLRenderer({ canvas, antialias: false, alpha: false, powerPreference: "high-performance", preserveDrawingBuffer: false });
    if (this.ownsRenderer) {
      this.renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
      this.renderer.outputColorSpace = THREE.SRGBColorSpace;
      this.renderer.setClearColor(0x020509, 1);
    }
    const gl = this.renderer.getContext();
    if (!this.renderer.capabilities.isWebGL2) throw new Error("Se necesita WebGL2");
    if (!this.renderer.extensions.has("EXT_color_buffer_float")) throw new Error("La GPU no admite render a texturas flotantes (EXT_color_buffer_float)");
    this.maxPointSize = gl.getParameter(gl.ALIASED_POINT_SIZE_RANGE)[1];

    this.object3D = new THREE.Group();
    this.object3D.name = "ATLAS_ParticleHumanoid";
    this.object3D.add(model.root);

    const skeleton = model.mesh.skeleton;
    if (!skeleton.boneTexture) skeleton.computeBoneTexture();

    // --- pase de skinning ---
    const W = model.partTexWidth, H = model.partTexHeight;
    const rtOpts = { type: THREE.FloatType, format: THREE.RGBAFormat, minFilter: THREE.NearestFilter, magFilter: THREE.NearestFilter, depthBuffer: false, stencilBuffer: false, generateMipmaps: false };
    this.rtPos = new THREE.WebGLRenderTarget(W, H, rtOpts);
    this.rtNrm = new THREE.WebGLRenderTarget(W, H, rtOpts);
    this.skinUniforms = {
      boneTexture: { value: skeleton.boneTexture },
      tVertPos: { value: model.tVertPos }, tVertSkinIndex: { value: model.tVertSkinIndex }, tVertSkinWeight: { value: model.tVertSkinWeight },
      tPartTri: { value: model.tPartTri }, tPartBary: { value: model.tPartBary },
      bindMatrix: { value: model.mesh.bindMatrix }, bindMatrixInverse: { value: model.mesh.bindMatrixInverse },
      meshMatrixWorld: { value: model.mesh.matrixWorld }, vertWidth: { value: model.vertTexWidth }, mode: { value: 0 },
    };
    this.skinMaterial = new THREE.ShaderMaterial({ glslVersion: THREE.GLSL3, uniforms: this.skinUniforms, vertexShader: skinVertexShader, fragmentShader: skinFragmentShader, depthTest: false, depthWrite: false });
    this.skinScene = new THREE.Scene();
    this.skinQuad = new THREE.Mesh(new THREE.PlaneGeometry(2, 2), this.skinMaterial);
    this.skinQuad.frustumCulled = false;
    this.skinScene.add(this.skinQuad);
    this.skinCamera = new THREE.OrthographicCamera(-1, 1, 1, -1, 0, 1);

    // --- puntos ---
    const n = model.particleCount;
    const geo = new THREE.BufferGeometry();
    geo.setAttribute("position", new THREE.BufferAttribute(new Float32Array(n * 3), 3)); // sólo para el conteo; la posición sale de tPos
    this.pointUniforms = {
      tPos: { value: this.rtPos.texture }, tNrm: { value: this.rtNrm.texture }, partWidth: { value: W },
      pointSize: { value: QUALITY[quality].pointSize }, pixelScale: { value: 500 }, depthBias: { value: 0.003 },
      regionScale: { value: REGION_SCALE }, brightness: { value: 1.0 },
      // 5E (neutros por defecto: mismo aspecto que la 5B)
      uTint: { value: new THREE.Color(0x38d6ff) }, uTintMix: { value: 0 }, uEnergyOrigin: { value: new THREE.Vector3(0, 1.3, 0) },
      uEnergyRadius: { value: 0 }, uEnergyWidth: { value: 0.07 }, uEnergyAmp: { value: 0 }, uEnergyColor: { value: new THREE.Color(0x38d6ff) },
    };
    this.pointMaterial = new THREE.ShaderMaterial({ glslVersion: THREE.GLSL3, uniforms: this.pointUniforms, vertexShader: pointsVertexShader, fragmentShader: pointsFragmentShader,
      transparent: true, depthWrite: false, depthTest: true, blending: THREE.AdditiveBlending });
    this.points = new THREE.Points(geo, this.pointMaterial);
    this.points.frustumCulled = false;
    this.points.renderOrder = 2;
    this.object3D.add(this.points);

    // --- malla original: sólo profundidad (oclusión) o sólida (comparación) ---
    this.depthMaterial = new THREE.MeshBasicMaterial({ colorWrite: false, depthWrite: true, polygonOffset: true, polygonOffsetFactor: 1, polygonOffsetUnits: 2 });
    this.solidMaterial = new THREE.MeshStandardMaterial({ color: 0x5f7488, roughness: 0.55, metalness: 0.15 });
    this.originalMaterial = model.mesh.material;
    model.mesh.renderOrder = 1;
    this.lights = new THREE.Group();
    this.lights.add(new THREE.HemisphereLight(0xbfdfff, 0x0a1420, 1.4));
    const key = new THREE.DirectionalLight(0xffffff, 2.2); key.position.set(1.5, 3, 2.5); this.lights.add(key);
    const rim = new THREE.DirectionalLight(0x66ccff, 1.5); rim.position.set(-2, 2, -2); this.lights.add(rim);
    this.object3D.add(this.lights);

    this.viewMode = "particles";   // particles | solid | overlay | split
    this.occlusion = true;
    this.pointSizeScale = 1;
    this.setQuality(quality);
    this.setViewMode("particles");
  }

  setQuality(name) {
    const q = QUALITY[name];
    if (!q) throw new Error(`Calidad desconocida: ${name}`);
    this.quality = name;
    this.count = Math.min(q.count, this.model.particleCount);
    this.rows = Math.ceil(this.count / this.model.partTexWidth);
    this.points.geometry.setDrawRange(0, this.count);
    this.pointUniforms.pointSize.value = q.pointSize * this.pointSizeScale;
  }

  /** Escala del tamaño de partícula respecto al de la calidad (1 = por defecto). */
  setPointSizeScale(s) { this.pointSizeScale = s; this.pointUniforms.pointSize.value = QUALITY[this.quality].pointSize * s; }

  setViewMode(mode) { this.viewMode = mode; }
  setOcclusion(on) { this.occlusion = on; }

  /** Pase de skinning: sólo las filas de la calidad activa. Llamar después de actualizar el mixer. */
  computeSkin() {
    const r = this.renderer;
    this.model.root.updateMatrixWorld(true);
    this.model.mesh.skeleton.update();
    const prevRT = r.getRenderTarget(), prevAutoClear = r.autoClear;
    const vp = (this._vp ||= new THREE.Vector4()).set(0, 0, this.model.partTexWidth, this.rows);   // 5G: sin asignaciones por frame
    r.autoClear = false;
    for (const [rt, mode] of [[this.rtPos, 0], [this.rtNrm, 1]]) {
      this.skinUniforms.mode.value = mode;
      rt.viewport.copy(vp); rt.scissor.copy(vp); rt.scissorTest = true;
      r.setRenderTarget(rt);
      r.render(this.skinScene, this.skinCamera);
    }
    r.setRenderTarget(prevRT);
    r.autoClear = prevAutoClear;
  }

  _configure(mode) {
    const mesh = this.model.mesh;
    if (mode === "solid") { mesh.visible = true; mesh.material = this.solidMaterial; this.points.visible = false; }
    else if (mode === "overlay") { mesh.visible = true; mesh.material = this.solidMaterial; this.points.visible = true; this.pointMaterial.depthTest = true; }
    else { mesh.visible = this.occlusion; mesh.material = this.depthMaterial; this.points.visible = true; }
    this.lights.visible = mesh.visible && mesh.material === this.solidMaterial;
  }

  /** Render completo del laboratorio (cuando el motor es dueño del renderer). */
  render(scene, camera) {
    const r = this.renderer;
    const size = r.getDrawingBufferSize(this._size ||= new THREE.Vector2());
    this.pointUniforms.pixelScale.value = size.y / (2 * Math.tan(THREE.MathUtils.degToRad(camera.fov) / 2));
    if (this.viewMode === "split") {
      const w = size.x / r.getPixelRatio(), h = size.y / r.getPixelRatio();
      r.setScissorTest(true);
      r.setViewport(0, 0, w, h);
      r.setScissor(0, 0, w / 2, h); this._configure("solid"); r.render(scene, camera);
      r.setScissor(w / 2, 0, w / 2, h); this._configure("particles"); r.render(scene, camera);
      r.setScissorTest(false);
    } else {
      this._configure(this.viewMode);
      if (this.post?.enabled && this.viewMode === "particles") this.post.render(() => r.render(scene, camera));   // 5E: bloom
      else r.render(scene, camera);
    }
  }

  /** 5E: bloom (sólo en la vista de partículas). */
  setBloom(on, opts = {}) {
    if (on && !this.post) this.post = new PostFX(this.renderer, opts);
    else if (this.post) this.post.set({ ...opts, enabled: !!on });
    this.bloomOn = !!on;
  }

  /** Lee las posiciones calculadas en GPU (validación). */
  readPositions(count = this.count) {
    const w = this.model.partTexWidth, rows = Math.ceil(count / w);
    const buf = new Float32Array(w * rows * 4);
    this.renderer.readRenderTargetPixels(this.rtPos, 0, 0, w, rows, buf);
    return buf;
  }

  memoryReport() {
    const W = this.model.partTexWidth, H = this.model.partTexHeight;
    const rt = W * H * 16 * 2;
    const pointsGeo = this.model.particleCount * 12;
    const boneTex = this.model.mesh.skeleton.boneTexture.image.width ** 2 * 16;
    const post = this.post?.enabled ? this.post.memoryBytes() : 0;     // 5E: búferes del bloom (si está activo)
    return { texturasDatosMB: this.model.memoryBytes() / 2 ** 20, renderTargetsMB: rt / 2 ** 20, geometriaPuntosMB: pointsGeo / 2 ** 20, texturaHuesosKB: boneTex / 1024,
      bloomMB: post / 2 ** 20, totalGPUaprox_MB: (this.model.memoryBytes() + rt + pointsGeo + boneTex + post) / 2 ** 20 };
  }

  dispose() {
    this.post?.dispose(); this.post = null;
    this.rtPos.dispose(); this.rtNrm.dispose();
    this.skinMaterial.dispose(); this.skinQuad.geometry.dispose();
    this.pointMaterial.dispose(); this.points.geometry.dispose();
    this.depthMaterial.dispose(); this.solidMaterial.dispose();
    this.model.mesh.material = this.originalMaterial;
    this.object3D.removeFromParent();
    if (this.ownsRenderer) { this.renderer.dispose(); this.renderer.forceContextLoss?.(); }
  }
}
