// ATLAS Fase 5B — muestreo determinista de partículas sobre la superficie del humanoide.
// Código puro (sin DOM ni Three.js): lo usan tools/build_particles.mjs (Node) y, como respaldo,
// HumanoidParticleModel en el navegador.
//
// Método:
//   1. Región de cada vértice según su hueso dominante (cabeza, manos, torso, brazos, piernas).
//   2. Peso de cada triángulo = área × densidad de su región (se usa la región más densa de sus 3 vértices,
//      para que los bordes de manos y cuello no queden más claros).
//   3. Candidatos estratificados sobre la distribución acumulada (3× el máximo de partículas).
//   4. Eliminación ponderada de muestras (Yuksel 2015) en tres etapas: HIGH → MEDIUM → LOW.
//      Cada etapa usa el radio de su propia densidad, así que el orden final
//      [LOW][MEDIUM−LOW][HIGH−MEDIUM] deja cualquier calidad uniforme: LOW es un prefijo de MEDIUM y éste de HIGH.
//      Sólo cuentan como vecinas las muestras con normales parecidas: dos superficies enfrentadas
//      (muslo contra muslo, dedo contra dedo) no se aclaran entre sí.
// Todo usa un generador con semilla fija: mismo GLB + mismos parámetros = mismas partículas, bit a bit.
// Sólo se usan operaciones con redondeo exacto según IEEE 754 (+ − × ÷ y Math.sqrt): Math.pow y Math.hypot
// pueden variar en el último bit entre versiones de motor JavaScript (Node frente a Chrome) y cambiarían el resultado.

export const REGIONS = ["head", "torso", "arm", "hand", "leg"];
export const DEFAULT_OPTIONS = {
  seed: 20261119,
  levels: { LOW: 16384, MEDIUM: 65536, HIGH: 131072 },
  candidateFactor: 3,
  // densidad relativa por unidad de área
  density: { head: 1.7, torso: 1.25, arm: 1.0, hand: 2.4, leg: 0.85 },
  normalCos: -0.2,   // vecinas sólo si dot(n_i, n_j) > este valor
};

export function regionOfBone(name) {
  const n = name.replace(/[.:]/g, "");
  if (/^DEF-(hand|palm|f_|thumb)/.test(n)) return 3;
  if (/^DEF-(upper_arm|forearm|shoulder_helper)/.test(n)) return 2;
  if (/^DEF-(thigh|shin|foot|toe)/.test(n)) return 4;
  if (/^DEF-spine00[456]/.test(n) || /^DEF-(neck|head)/.test(n)) return 0;
  return 1; // columna, pelvis, pecho, hombros
}

export function mulberry32(seed) {
  let a = seed >>> 0;
  return () => {
    a = (a + 0x6D2B79F5) >>> 0;
    let t = a;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

export function fnv1a(bytes) {
  let h = 0x811c9dc5;
  for (let i = 0; i < bytes.length; i++) { h ^= bytes[i]; h = Math.imul(h, 0x01000193); }
  return (h >>> 0).toString(16).padStart(8, "0");
}

/** Montículo de máximos indexado (permite bajar la clave de un elemento). */
class IndexedMaxHeap {
  constructor(keys, ids) {
    this.k = keys; this.h = Int32Array.from(ids); this.n = ids.length;
    this.pos = new Int32Array(keys.length).fill(-1);
    for (let i = 0; i < this.n; i++) this.pos[this.h[i]] = i;
    for (let i = (this.n >> 1) - 1; i >= 0; i--) this.down(i);
  }
  less(a, b) { const ka = this.k[this.h[a]], kb = this.k[this.h[b]]; return ka < kb || (ka === kb && this.h[a] > this.h[b]); }
  swap(a, b) { const t = this.h[a]; this.h[a] = this.h[b]; this.h[b] = t; this.pos[this.h[a]] = a; this.pos[this.h[b]] = b; }
  up(i) { while (i > 0) { const p = (i - 1) >> 1; if (!this.less(p, i)) break; this.swap(p, i); i = p; } }
  down(i) { for (;;) { const l = 2 * i + 1, r = l + 1; let m = i; if (l < this.n && this.less(m, l)) m = l; if (r < this.n && this.less(m, r)) m = r; if (m === i) return; this.swap(i, m); i = m; } }
  pop() { const top = this.h[0]; this.n--; if (this.n > 0) { this.h[0] = this.h[this.n]; this.pos[this.h[0]] = 0; this.down(0); } this.pos[top] = -1; return top; }
  update(id) { const i = this.pos[id]; if (i < 0) return; this.up(i); this.down(this.pos[id]); }
}

/**
 * @param {{positions: Float32Array, index: Uint32Array|Uint16Array, skinIndex: ArrayLike<number>, skinWeight: ArrayLike<number>, boneNames: string[]}} mesh
 * @returns {{tri: Uint32Array, bary: Float32Array, region: Uint8Array, seed: Float32Array, order: object, stats: object}}
 */
export function sampleParticles(mesh, options = {}) {
  const opt = { ...DEFAULT_OPTIONS, ...options, density: { ...DEFAULT_OPTIONS.density, ...(options.density || {}) }, levels: { ...DEFAULT_OPTIONS.levels, ...(options.levels || {}) } };
  const { positions: P, index: I, skinIndex: SI, skinWeight: SW, boneNames } = mesh;
  const nv = P.length / 3, nt = I.length / 3;
  const rng = mulberry32(opt.seed);
  const dens = REGIONS.map(r => opt.density[r]);
  const boneRegion = boneNames.map(regionOfBone);

  // 1. región por vértice (hueso dominante)
  const vReg = new Uint8Array(nv);
  for (let v = 0; v < nv; v++) {
    let best = -1, bi = 0;
    for (let k = 0; k < 4; k++) { const w = SW[v * 4 + k]; if (w > best) { best = w; bi = SI[v * 4 + k]; } }
    vReg[v] = boneRegion[bi];
  }
  // 2. peso por triángulo
  const tReg = new Uint8Array(nt), tN = new Float32Array(nt * 3), cum = new Float64Array(nt);
  let acc = 0, areaTot = 0;
  const areaReg = new Float64Array(5);
  for (let t = 0; t < nt; t++) {
    const a = I[t * 3] * 3, b = I[t * 3 + 1] * 3, c = I[t * 3 + 2] * 3;
    const ux = P[b] - P[a], uy = P[b + 1] - P[a + 1], uz = P[b + 2] - P[a + 2];
    const vx = P[c] - P[a], vy = P[c + 1] - P[a + 1], vz = P[c + 2] - P[a + 2];
    const nx = uy * vz - uz * vy, ny = uz * vx - ux * vz, nz = ux * vy - uy * vx;
    const len = Math.sqrt(nx * nx + ny * ny + nz * nz), area = len / 2;
    if (len > 0) { tN[t * 3] = nx / len; tN[t * 3 + 1] = ny / len; tN[t * 3 + 2] = nz / len; }
    let r = vReg[I[t * 3]];
    for (let k = 1; k < 3; k++) { const rk = vReg[I[t * 3 + k]]; if (dens[rk] > dens[r]) r = rk; }
    tReg[t] = r; areaTot += area; areaReg[r] += area;
    acc += area * dens[r]; cum[t] = acc;
  }
  const weightedArea = acc;

  // 3. candidatos estratificados
  const N = opt.levels.HIGH, M = Math.round(N * opt.candidateFactor);
  const cTri = new Uint32Array(M), cBary = new Float32Array(M * 2), cPos = new Float32Array(M * 3), cReg = new Uint8Array(M);
  for (let k = 0; k < M; k++) {
    const target = (k + rng()) / M * weightedArea;
    let lo = 0, hi = nt - 1;
    while (lo < hi) { const mid = (lo + hi) >> 1; if (cum[mid] < target) lo = mid + 1; else hi = mid; }
    let r1 = rng(), r2 = rng();
    const s = Math.sqrt(r1); const u = 1 - s, v = s * (1 - r2); // pesos de b y c: (1-u-v) es a
    const a = I[lo * 3] * 3, b = I[lo * 3 + 1] * 3, c = I[lo * 3 + 2] * 3;
    const wa = 1 - u - v;
    cTri[k] = lo; cBary[k * 2] = u; cBary[k * 2 + 1] = v; cReg[k] = tReg[lo];
    for (let d = 0; d < 3; d++) cPos[k * 3 + d] = wa * P[a + d] + u * P[b + d] + v * P[c + d];
  }

  // 4. eliminación ponderada por etapas
  const levels = Object.entries(opt.levels).sort((x, y) => y[1] - x[1]); // HIGH, MEDIUM, LOW
  let alive = Int32Array.from({ length: M }, (_, i) => i);
  const removedOrder = []; // [ids eliminados en la etapa HIGH (descartados)], luego por etapa
  const stageRemoved = {};
  for (const [name, count] of levels) {
    const ids = alive;
    // radio por región para esta densidad final: r = sqrt(A_w / (2·sqrt(3)·count·dens))
    const rReg = dens.map(dv => Math.sqrt(weightedArea / (2 * Math.sqrt(3) * count * dv)));
    const rMax = Math.max(...rReg);
    const cell = 2 * rMax;
    const grid = new Map();
    const key = (x, y, z) => ((Math.floor(x / cell) + 1024) * 2048 + (Math.floor(y / cell) + 1024)) * 2048 + (Math.floor(z / cell) + 1024);
    for (const id of ids) { const k = key(cPos[id * 3], cPos[id * 3 + 1], cPos[id * 3 + 2]); let a = grid.get(k); if (!a) grid.set(k, a = []); a.push(id); }
    // vecinas
    const nbStart = new Int32Array(M + 1), nbList = [], nbW = [];
    const w = new Float64Array(M);
    const isAlive = new Uint8Array(M); for (const id of ids) isAlive[id] = 1;
    const neighbors = new Map();
    for (const i of ids) {
      const x = cPos[i * 3], y = cPos[i * 3 + 1], z = cPos[i * 3 + 2];
      const cx = Math.floor(x / cell), cy = Math.floor(y / cell), cz = Math.floor(z / cell);
      const list = [];
      const ti = cTri[i] * 3;
      for (let dx = -1; dx <= 1; dx++) for (let dy = -1; dy <= 1; dy++) for (let dz = -1; dz <= 1; dz++) {
        const a = grid.get(((cx + dx + 1024) * 2048 + (cy + dy + 1024)) * 2048 + (cz + dz + 1024)); if (!a) continue;
        for (const j of a) {
          if (j === i) continue;
          const rij = 0.5 * (rReg[cReg[i]] + rReg[cReg[j]]);
          const ex = cPos[j * 3] - x, ey = cPos[j * 3 + 1] - y, ez = cPos[j * 3 + 2] - z;
          const d = Math.sqrt(ex * ex + ey * ey + ez * ez);
          if (d >= 2 * rij) continue;
          const tj = cTri[j] * 3;
          if (tN[ti] * tN[tj] + tN[ti + 1] * tN[tj + 1] + tN[ti + 2] * tN[tj + 2] <= opt.normalCos) continue;
          const q1 = 1 - d / (2 * rij), q2 = q1 * q1, q4 = q2 * q2, wij = q4 * q4;
          list.push(j, wij); w[i] += wij;
        }
      }
      neighbors.set(i, list);
    }
    const heap = new IndexedMaxHeap(w, ids);
    const removeCount = ids.length - count;
    const removed = [];
    for (let r = 0; r < removeCount; r++) {
      const i = heap.pop(); isAlive[i] = 0; removed.push(i);
      const list = neighbors.get(i);
      for (let q = 0; q < list.length; q += 2) { const j = list[q]; if (!isAlive[j]) continue; w[j] -= list[q + 1]; heap.update(j); }
    }
    stageRemoved[name] = removed;
    alive = Int32Array.from(ids.filter(id => isAlive[id]));
  }
  // orden final: LOW (supervivientes de la última etapa) + eliminadas en la etapa LOW (= MEDIUM−LOW) + eliminadas en la etapa MEDIUM (= HIGH−MEDIUM)
  // Dentro de cada bloque, las eliminadas más tarde (más uniformes) van primero.
  const [hi, md, lw] = levels.map(l => l[0]);
  const sortSpatial = arr => Array.from(arr).sort((a, b) => a - b); // determinista
  const order = [...sortSpatial(alive), ...stageRemoved[lw].slice().reverse(), ...stageRemoved[md].slice().reverse()];
  const count = order.length;
  const tri = new Uint32Array(count), bary = new Float32Array(count * 2), region = new Uint8Array(count), seed = new Float32Array(count);
  for (let k = 0; k < count; k++) {
    const id = order[k];
    tri[k] = cTri[id]; bary[k * 2] = cBary[id * 2]; bary[k * 2 + 1] = cBary[id * 2 + 1]; region[k] = cReg[id];
    seed[k] = rng();
  }
  const perRegion = {};
  for (const [name, n] of Object.entries(opt.levels)) {
    const c = [0, 0, 0, 0, 0]; for (let k = 0; k < n; k++) c[region[k]]++;
    perRegion[name] = Object.fromEntries(REGIONS.map((r, i) => [r, c[i]]));
  }
  return {
    tri, bary, region, seed,
    stats: {
      vertices: nv, triangles: nt, candidates: M, levels: opt.levels, seed: opt.seed, density: opt.density,
      areaM2: areaTot, areaByRegionM2: Object.fromEntries(REGIONS.map((r, i) => [r, areaReg[i]])), perRegion,
    },
  };
}

/** Empaqueta el resultado en un único buffer binario (orden: tri u32, bary f32×2, seed f32, region u8). */
export function packParticles(res) {
  const n = res.tri.length;
  const buf = new ArrayBuffer(n * 4 + n * 8 + n * 4 + n);
  new Uint32Array(buf, 0, n).set(res.tri);
  new Float32Array(buf, n * 4, n * 2).set(res.bary);
  new Float32Array(buf, n * 12, n).set(res.seed);
  new Uint8Array(buf, n * 16, n).set(res.region);
  return buf;
}
export function unpackParticles(buf, n) {
  return {
    tri: new Uint32Array(buf, 0, n), bary: new Float32Array(buf, n * 4, n * 2),
    seed: new Float32Array(buf, n * 12, n), region: new Uint8Array(buf, n * 16, n),
  };
}
