// ATLAS Fase 5B — carga del GLB oficial, inspección y datos de partículas para la GPU.
// No modifica el GLB: lo lee, comprueba su contenido y construye texturas de datos (vértices y partículas).
import * as THREE from "../../vendor/three.module.js";
import { GLTFLoader } from "../../vendor/GLTFLoader.js";
import { sampleParticles, unpackParticles, DEFAULT_OPTIONS } from "./ParticleSampler.js";

export const BODY_CLIPS = ["Idle", "Talking", "Explaining", "Thinking", "Listening", "Waving", "Nodding", "Pointing", "Presenting", "Shrugging"];
export const GESTURES = { Open: "Abierta", Relaxed: "Relajada", Fist: "Puno", Point: "Senalar", Pinch: "Pinza" };
export const HAND_CLIPS = Object.values(GESTURES).flatMap(g => [`Hand_${g}_L`, `Hand_${g}_R`]);
export const EXPECTED_BONES = 73;
export const PARTICLE_TEX_WIDTH = 512;
const VERT_TEX_WIDTH = 256;

async function sha256Hex(buffer) {
  if (!globalThis.crypto?.subtle) return null; // http (no seguro) fuera de localhost: no se puede comprobar
  const h = await crypto.subtle.digest("SHA-256", buffer);
  return Array.from(new Uint8Array(h), b => b.toString(16).padStart(2, "0")).join("");
}

function floatTexture(data, width, height) {
  const t = new THREE.DataTexture(data, width, height, THREE.RGBAFormat, THREE.FloatType);
  t.minFilter = t.magFilter = THREE.NearestFilter;
  t.generateMipmaps = false;
  t.needsUpdate = true;
  return t;
}

export class HumanoidParticleModel {
  /**
   * @param {{glbUrl: string, dataUrl?: string, onProgress?: (msg:string)=>void}} opts
   */
  static async load({ glbUrl, dataUrl, onProgress = () => {} }) {
    const m = new HumanoidParticleModel();
    onProgress("Descargando GLB…");
    const glbBuf = await (await fetch(glbUrl)).arrayBuffer();
    m.glbBytes = glbBuf.byteLength;
    m.glbSha256 = await sha256Hex(glbBuf);
    onProgress("Leyendo GLB…");
    m.gltf = await new Promise((res, rej) => new GLTFLoader().parse(glbBuf, "", res, rej));
    m.root = m.gltf.scene;
    m.root.traverse(o => { if (o.isSkinnedMesh && !m.mesh) m.mesh = o; });
    if (!m.mesh) throw new Error("El GLB no contiene una SkinnedMesh");
    m.mesh.frustumCulled = false;
    m.report = m.inspect();
    m.buildVertexTextures();

    let particles = null;
    if (dataUrl) {
      try {
        onProgress("Cargando distribución de partículas…");
        const meta = await (await fetch(dataUrl + ".json")).json();
        if (m.glbSha256 && meta.glbSha256 !== m.glbSha256) throw new Error("los datos de partículas son de otro GLB");
        const bin = await (await fetch(dataUrl + ".bin")).arrayBuffer();
        particles = { ...unpackParticles(bin, meta.count), meta, source: "archivo" };
      } catch (err) {
        console.warn("[ATLAS] datos precalculados no válidos, se regeneran:", err.message);
      }
    }
    if (!particles) {
      onProgress("Generando distribución de partículas (determinista)…");
      const t0 = performance.now();
      const res = sampleParticles(m.meshArrays());
      particles = { ...res, meta: { count: res.tri.length, options: DEFAULT_OPTIONS, stats: res.stats, generatedMs: performance.now() - t0 }, source: "generado" };
    }
    m.particles = particles;
    m.buildParticleTextures();
    onProgress("Listo");
    return m;
  }

  /** Copia compacta de los atributos (los del GLB pueden venir intercalados). */
  meshArrays() {
    const g = this.mesh.geometry;
    const compact = (a, T) => { const o = new T(a.count * a.itemSize); for (let i = 0; i < a.count; i++) for (let k = 0; k < a.itemSize; k++) o[i * a.itemSize + k] = a.getComponent(i, k); return o; };
    return {
      positions: compact(g.attributes.position, Float32Array), index: g.index.array,
      skinIndex: compact(g.attributes.skinIndex, Uint16Array), skinWeight: compact(g.attributes.skinWeight, Float32Array),
      boneNames: this.mesh.skeleton.bones.map(b => b.name),
    };
  }

  inspect() {
    const meshes = [], materials = new Set();
    this.root.traverse(o => {
      if (o.isMesh) {
        meshes.push({ name: o.name, skinned: !!o.isSkinnedMesh, vertices: o.geometry.attributes.position.count, triangles: (o.geometry.index ? o.geometry.index.count : o.geometry.attributes.position.count) / 3 });
        (Array.isArray(o.material) ? o.material : [o.material]).forEach(mt => materials.add(`${mt.name || "(sin nombre)"} · ${mt.type}`));
      }
    });
    const clipNames = this.gltf.animations.map(a => a.name);
    const bones = this.mesh.skeleton.bones;
    const g = this.mesh.geometry;
    let maxInfluences = 0;
    const sw = g.attributes.skinWeight;
    for (let i = 0; i < sw.count; i++) { let n = 0; for (let k = 0; k < 4; k++) if (sw.getComponent(i, k) > 0) n++; maxInfluences = Math.max(maxInfluences, n); }
    const checks = {
      huesos: { esperado: EXPECTED_BONES, encontrado: bones.length, ok: bones.length === EXPECTED_BONES },
      clips_cuerpo: { faltan: BODY_CLIPS.filter(n => !clipNames.includes(n)), ok: BODY_CLIPS.every(n => clipNames.includes(n)) },
      clips_mano: { faltan: HAND_CLIPS.filter(n => !clipNames.includes(n)), ok: HAND_CLIPS.every(n => clipNames.includes(n)) },
      clips_extra: clipNames.filter(n => !BODY_CLIPS.includes(n) && !HAND_CLIPS.includes(n)),
      auxiliares_hombro: bones.filter(b => /shoulder_helper/.test(b.name)).map(b => b.name),
    };
    return {
      meshes, materials: [...materials], bones: bones.length, boneNames: bones.map(b => b.name), maxInfluences,
      clips: this.gltf.animations.map(a => ({ name: a.name, duration: +a.duration.toFixed(3), tracks: a.tracks.length })),
      checks, ok: checks.huesos.ok && checks.clips_cuerpo.ok && checks.clips_mano.ok,
    };
  }

  buildVertexTextures() {
    const a = this.meshArrays();
    const nv = a.positions.length / 3, h = Math.ceil(nv / VERT_TEX_WIDTH);
    const pos = new Float32Array(VERT_TEX_WIDTH * h * 4), si = new Float32Array(VERT_TEX_WIDTH * h * 4), sw = new Float32Array(VERT_TEX_WIDTH * h * 4);
    for (let i = 0; i < nv; i++) {
      pos.set([a.positions[i * 3], a.positions[i * 3 + 1], a.positions[i * 3 + 2], 1], i * 4);
      for (let k = 0; k < 4; k++) { si[i * 4 + k] = a.skinIndex[i * 4 + k]; sw[i * 4 + k] = a.skinWeight[i * 4 + k]; }
    }
    this.vertexCount = nv;
    this.vertTexWidth = VERT_TEX_WIDTH;
    this.tVertPos = floatTexture(pos, VERT_TEX_WIDTH, h);
    this.tVertSkinIndex = floatTexture(si, VERT_TEX_WIDTH, h);
    this.tVertSkinWeight = floatTexture(sw, VERT_TEX_WIDTH, h);
    this.index = a.index;
  }

  buildParticleTextures() {
    const P = this.particles, n = P.tri.length;
    const w = PARTICLE_TEX_WIDTH, h = Math.ceil(n / w);
    const tri = new Float32Array(w * h * 4), bary = new Float32Array(w * h * 4);
    const I = this.index;
    for (let k = 0; k < n; k++) {
      const t = P.tri[k] * 3;
      tri[k * 4] = I[t]; tri[k * 4 + 1] = I[t + 1]; tri[k * 4 + 2] = I[t + 2]; tri[k * 4 + 3] = P.region[k];
      bary[k * 4] = P.bary[k * 2]; bary[k * 4 + 1] = P.bary[k * 2 + 1]; bary[k * 4 + 2] = P.seed[k];
    }
    this.particleCount = n;
    this.partTexWidth = w; this.partTexHeight = h;
    this.tPartTri = floatTexture(tri, w, h);
    this.tPartBary = floatTexture(bary, w, h);
    this.levels = P.meta.options.levels;
  }

  /** Posición deformada de una partícula calculada en CPU (sólo para validación). */
  cpuParticlePosition(k, target = new THREE.Vector3()) {
    const P = this.particles, t = P.tri[k] * 3, I = this.index;
    const u = P.bary[k * 2], v = P.bary[k * 2 + 1], w = 1 - u - v;
    const a = new THREE.Vector3(), b = new THREE.Vector3(), c = new THREE.Vector3();
    this.mesh.getVertexPosition(I[t], a).applyMatrix4(this.mesh.matrixWorld);
    this.mesh.getVertexPosition(I[t + 1], b).applyMatrix4(this.mesh.matrixWorld);
    this.mesh.getVertexPosition(I[t + 2], c).applyMatrix4(this.mesh.matrixWorld);
    return target.set(a.x * w + b.x * u + c.x * v, a.y * w + b.y * u + c.y * v, a.z * w + b.z * u + c.z * v);
  }

  /** Memoria aproximada de las texturas de datos (bytes). */
  memoryBytes() {
    const tex = t => t.image.width * t.image.height * 16;
    return tex(this.tVertPos) * 3 + tex(this.tPartTri) * 2;
  }

  dispose() {
    for (const t of [this.tVertPos, this.tVertSkinIndex, this.tVertSkinWeight, this.tPartTri, this.tPartBary]) t?.dispose();
    this.root?.traverse(o => { if (o.isMesh) { o.geometry.dispose(); (Array.isArray(o.material) ? o.material : [o.material]).forEach(m => m.dispose()); } });
    this.mesh?.skeleton?.dispose();
  }
}
