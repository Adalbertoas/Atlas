// ATLAS Fase 5E — núcleo de energía 3D integrado en el pecho del humanoide de partículas.
// Elementos (todos geometría 3D real animada en la GPU, nada de imágenes superpuestas):
//   envoltura deformada + núcleo brillante · plasma interior (puntos) · partículas orbitales / flujo direccional ·
//   3 anillos de energía con pulsos que los recorren · ondas esféricas de emisión/recepción · destellos (chispas) ·
//   campo de partículas alrededor del avatar · onda de energía que recorre el cuerpo de partículas (uniforms del motor).
// Estados: idle, listening, thinking, executing, speaking, error (CoreStates.js). Transiciones con suavizado exponencial.
// Audio: setAudioLevel(0–1) por frame (amplitud real); si deja de llegar, el nivel cae a 0 (no se queda "hablando").
import * as THREE from "../../vendor/three.module.js";
import * as S from "./coreShaders.glsl.js";
import { CORE_PRESETS, STATES, ENTER_TAU, LEAVE_ERROR_TAU, DEFAULT_CONTROLS } from "./CoreStates.js";

const QUALITY_SCALE = { LOW: 0.45, MEDIUM: 0.75, HIGH: 1 };
const BASE = { plasma: 1800, orbit: 3200, field: 6000, sparks: 180 };
const N_WAVES = 6, N_BURSTS = 4, AUDIO_STALE_S = 0.25;
const NUM_KEYS = Object.keys(CORE_PRESETS.idle).filter(k => typeof CORE_PRESETS.idle[k] === "number" && !/color|Tint$/.test(k));
const lin = hex => new THREE.Color().setHex(hex, THREE.LinearSRGBColorSpace);   // los shaders escriben el color tal cual

function rng(seed) { let a = seed >>> 0; return () => { a = (a + 0x6D2B79F5) >>> 0; let t = a; t = Math.imul(t ^ (t >>> 15), t | 1); t ^= t + Math.imul(t ^ (t >>> 7), t | 61); return ((t ^ (t >>> 14)) >>> 0) / 4294967296; }; }

export class AtlasCore extends EventTarget {
  /**
   * @param {{quality?: string, pixelScale: {value:number}, anchorBone?: THREE.Object3D, anchorWorld?: THREE.Vector3,
   *          bodyUniforms?: object, seed?: number, field?: {size: number[], center: number[]}}} o
   */
  constructor({ quality = "MEDIUM", pixelScale, anchorBone = null, anchorWorld = new THREE.Vector3(0, 1.3, 0.05), bodyUniforms = null, seed = 20261119,
    field = { size: [3.2, 2.6, 2.4], center: [0, 1.15, 0] } } = {}) {
    super();
    this.rnd = rng(seed);
    this.bodyU = bodyUniforms;
    this.object3D = new THREE.Group(); this.object3D.name = "ATLAS_Core";
    this.core = new THREE.Group(); this.object3D.add(this.core);
    this.anchorBone = anchorBone;
    this.anchorLocal = new THREE.Vector3();
    if (anchorBone) { anchorBone.updateWorldMatrix(true, false); this.anchorLocal.copy(anchorWorld).applyMatrix4(new THREE.Matrix4().copy(anchorBone.matrixWorld).invert()); }
    else this.core.position.copy(anchorWorld);

    this.state = "idle"; this.prevState = "idle";
    this.controls = { ...DEFAULT_CONTROLS };
    this.p = {}; this.t = {}; this.v = {};
    for (const k of NUM_KEYS) { this.p[k] = this.t[k] = CORE_PRESETS.idle[k]; this.v[k] = 0; }
    this.col = { color: lin(CORE_PRESETS.idle.color), color2: lin(CORE_PRESETS.idle.color2), bodyTint: lin(CORE_PRESETS.idle.bodyTint) };
    this.colT = { color: this.col.color.clone(), color2: this.col.color2.clone(), bodyTint: this.col.bodyTint.clone() };
    this.bodyTintMix = 0; this.vTintMix = 0;
    this.vCol = { color: new THREE.Vector3(), color2: new THREE.Vector3(), bodyTint: new THREE.Vector3() };
    this.tau = ENTER_TAU.idle;
    this.phase = { orbit: 0, flow: 0, noise: 0, ring: 0, pulse: 0, swirl: 0, waveAcc: 0 };
    this.audio = { raw: 0, rawT: -1e9, env: 0, slow: 0, lastOnset: -1e9, onsets: 0 };
    this.time = 0; this.pulse = 0;
    this.stats = { waves: 0, bursts: 0, onsets: 0, stateChanges: 0 };

    const U = this.U = {
      uTime: { value: 0 }, uNoiseT: { value: 0 }, uOrbitPhase: { value: 0 }, uFlowPhase: { value: 0 }, uPulse: { value: 0 }, uAudio: { value: 0 },
      uTurb: { value: 0.2 }, uIntensity: { value: 1 }, uBrightness: { value: 1 }, uScale: { value: 1 }, uFlow: { value: 0 }, uAudioGain: { value: 0 },
      uPixelScale: pixelScale || { value: 500 }, uColor: { value: this.col.color.clone() }, uColor2: { value: this.col.color2.clone() },
      uFlowDir: { value: new THREE.Vector3(0.35, 0.85, 0.4).normalize() },
    };
    const add = { blending: THREE.AdditiveBlending, transparent: true, depthWrite: false, depthTest: false, glslVersion: THREE.GLSL3 };
    this.materials = []; this.geometries = [];
    const mat = (o) => { const m = new THREE.ShaderMaterial({ ...add, ...o }); this.materials.push(m); return m; };
    const geo = g => { this.geometries.push(g); return g; };

    // envoltura y núcleo
    this.shell = new THREE.Mesh(geo(new THREE.IcosahedronGeometry(0.055, 5)), mat({ uniforms: { ...U }, vertexShader: S.shellVS, fragmentShader: S.shellFS }));
    this.kernel = new THREE.Mesh(geo(new THREE.IcosahedronGeometry(0.022, 3)), mat({ uniforms: { ...U }, vertexShader: S.shellVS, fragmentShader: S.kernelFS }));
    this.shell.renderOrder = 5; this.kernel.renderOrder = 6;
    this.core.add(this.shell, this.kernel);

    // plasma, órbitas
    this.plasma = this._points(BASE.plasma, 4, "aSeed", () => [this.rnd(), this.rnd(), this.rnd(), this.rnd()], S.plasmaVS, { ...U });
    const og = new THREE.BufferGeometry(), no = BASE.orbit, aO = new Float32Array(no * 4), aS = new Float32Array(no * 2);
    const bands = [0.085, 0.12, 0.165, 0.21];
    for (let i = 0; i < no; i++) {
      const band = bands[i % bands.length];
      aO[i * 4] = band * (0.92 + 0.16 * this.rnd()); aO[i * 4 + 1] = (this.rnd() - 0.5) * 0.5 + (i % 4) * 0.55; aO[i * 4 + 2] = this.rnd() * Math.PI * 2; aO[i * 4 + 3] = this.rnd() * Math.PI * 2;
      aS[i * 2] = (0.55 + 0.9 * this.rnd()) * (i % 2 ? 1 : -1) * (1.2 - band * 2.5); aS[i * 2 + 1] = this.rnd();
    }
    og.setAttribute("position", new THREE.BufferAttribute(new Float32Array(no * 3), 3));
    og.setAttribute("aOrbit", new THREE.BufferAttribute(aO, 4)); og.setAttribute("aSpeed", new THREE.BufferAttribute(aS, 2));
    this.orbit = new THREE.Points(geo(og), mat({ uniforms: { ...U }, vertexShader: S.orbitVS, fragmentShader: S.pointFS }));
    this.orbit.frustumCulled = false; this.orbit.renderOrder = 7; this.core.add(this.orbit);

    // anillos
    this.rings = [0.11, 0.155, 0.2].map((r, i) => {
      const u = { ...U, uRingPhase: { value: 0 }, uRingDash: { value: 3 + i * 2 }, uRingColor: { value: new THREE.Color() } };
      const m = new THREE.Mesh(geo(new THREE.TorusGeometry(r, 0.0013 + i * 0.0003, 6, 192)), mat({ uniforms: u, vertexShader: S.ringVS, fragmentShader: S.ringFS }));
      m.userData = { tilt: [0.35 + i * 0.45, i * 0.9], dir: i % 2 ? -1 : 1, k: 1 + i * 0.35 }; m.renderOrder = 6;
      this.core.add(m); return m;
    });

    // ondas (pool)
    const wg = geo(new THREE.SphereGeometry(1, 40, 20));
    this.waves = Array.from({ length: N_WAVES }, () => {
      const m = new THREE.Mesh(wg, mat({ uniforms: { uR: { value: 0.1 }, uA: { value: 0 }, uC: { value: new THREE.Color() } }, vertexShader: S.waveVS, fragmentShader: S.waveFS }));
      m.visible = false; m.renderOrder = 4; m.userData = { age: 0, dur: 1.4, dir: 1, amp: 0 }; this.core.add(m); return m;
    });

    // destellos (pool de ráfagas)
    this.bursts = Array.from({ length: N_BURSTS }, () => {
      const g = new THREE.BufferGeometry(), n = BASE.sparks, d = new Float32Array(n * 4);
      for (let i = 0; i < n; i++) { const v = new THREE.Vector3(this.rnd() * 2 - 1, this.rnd() * 2 - 1, this.rnd() * 2 - 1).normalize(); d.set([v.x, v.y, v.z, 0.4 + this.rnd()], i * 4); }
      g.setAttribute("position", new THREE.BufferAttribute(new Float32Array(n * 3), 3)); g.setAttribute("aDir", new THREE.BufferAttribute(d, 4));
      const m = new THREE.Points(geo(g), mat({ uniforms: { uAge: { value: 99 }, uPixelScale: U.uPixelScale, uScale: U.uScale, uSparkColor: { value: new THREE.Color() } }, vertexShader: S.sparkVS, fragmentShader: S.pointFS }));
      m.frustumCulled = false; m.visible = false; m.renderOrder = 8; this.core.add(m); return m;
    });

    // campo de partículas (espacio del avatar; con prueba de profundidad: el cuerpo lo tapa)
    const [sx, sy, sz] = field.size, [cx, cy, cz] = field.center;
    this.fieldU = { ...U, uCore: { value: new THREE.Vector3() }, uFieldSwirl: { value: 0 } };
    this.field = this._points(BASE.field, 4, "aSeed", () => {
      let x, z; do { x = (this.rnd() - 0.5) * sx; z = (this.rnd() - 0.5) * sz; } while (Math.abs(x) < 0.28 && Math.abs(z) < 0.2);   // no dentro del cuerpo
      return [cx + x, cy + (this.rnd() - 0.5) * sy, cz + z, this.rnd()];
    }, S.fieldVS, this.fieldU, false);
    this.field.material.depthTest = true; this.field.renderOrder = 1;
    this.object3D.add(this.field); this.core.remove(this.field);

    this.quality = quality; this.setQuality(quality);
    this.update(0);
  }

  _points(n, size, attr, gen, vs, uniforms, inCore = true) {
    const g = new THREE.BufferGeometry(), a = new Float32Array(n * size);
    for (let i = 0; i < n; i++) a.set(gen(i), i * size);
    g.setAttribute("position", new THREE.BufferAttribute(new Float32Array(n * 3), 3)); g.setAttribute(attr, new THREE.BufferAttribute(a, size));
    this.geometries.push(g);
    const m = new THREE.ShaderMaterial({ glslVersion: THREE.GLSL3, uniforms, vertexShader: vs, fragmentShader: S.pointFS, blending: THREE.AdditiveBlending, transparent: true, depthWrite: false, depthTest: false });
    this.materials.push(m);
    const p = new THREE.Points(g, m); p.frustumCulled = false; p.renderOrder = 7;
    if (inCore) this.core.add(p);
    p.userData.n = n;
    return p;
  }

  // ---------------- API ----------------
  setState(state) {
    const s = STATES.includes(state) ? state : "idle";
    if (s === this.state) return;
    this.prevState = this.state; this.state = s; this.stats.stateChanges++;
    const P = CORE_PRESETS[s];
    for (const k of NUM_KEYS) this.t[k] = P[k];
    this.colT.color.copy(lin(P.color)); this.colT.color2.copy(lin(P.color2)); this.colT.bodyTint.copy(lin(P.bodyTint));
    this.tau = this.prevState === "error" ? LEAVE_ERROR_TAU : ENTER_TAU[s];
    if (s === "executing") this.flash(P.color, 1);
    if (s === "error") { this.flash(P.color, 1.2); this.spawnWave(1, 1); }
    if (s === "listening") this.spawnWave(-1, 0.8);
    if (s === "thinking") this.flash(P.color2, 0.5);
    this.dispatchEvent(new CustomEvent("state", { detail: { state: s, previous: this.prevState } }));
  }

  /** Controles del usuario: intensity, speed, size, density (0.05–1), brightness, waveAmplitude, color (hex | null), colorMix (0–1). */
  setControls(c = {}) {
    Object.assign(this.controls, c);
    const k = this.controls;
    k.density = Math.max(0.05, Math.min(1, k.density)); k.speed = Math.max(0, k.speed); k.size = Math.max(0.2, k.size);
    this._applyCounts();
  }

  setQuality(q) { this.quality = QUALITY_SCALE[q] ? q : "MEDIUM"; this._applyCounts(); }
  _applyCounts() {
    const f = QUALITY_SCALE[this.quality] * this.controls.density;
    for (const p of [this.plasma, this.orbit, this.field]) p.geometry.setDrawRange(0, Math.max(16, Math.floor((p.userData.n ?? p.geometry.attributes.position.count) * f)));
    this.counts = { plasma: this.plasma.geometry.drawRange.count, orbit: this.orbit.geometry.drawRange.count, field: this.field.geometry.drawRange.count };
  }

  /** Nivel de audio real (0–1), una vez por frame mientras haya audio. */
  setAudioLevel(level, tSec = this.time) { this.audio.raw = Math.max(0, Math.min(1, +level || 0)); this.audio.rawT = tSec; }

  /** Ráfaga de chispas. */
  flash(hex = 0xffffff, strength = 1) {
    const b = this.bursts.reduce((a, x) => (x.material.uniforms.uAge.value > a.material.uniforms.uAge.value ? x : a), this.bursts[0]);
    b.material.uniforms.uAge.value = 0; b.material.uniforms.uSparkColor.value.copy(lin(hex)).multiplyScalar(strength);
    b.visible = true; this.stats.bursts++;
  }

  /** Onda: dir = 1 emisión (se expande), −1 recepción (se contrae). */
  spawnWave(dir = 1, amp = 1) {
    const w = this.waves.reduce((a, x) => (!x.visible ? x : a.visible && x.userData.age > a.userData.age ? x : a), this.waves[0]);
    Object.assign(w.userData, { age: 0, dur: 1.4, dir, amp }); w.visible = true; this.stats.waves++;
    if (dir > 0 && this.bodyU) this.bodyWave = { r: 0.02, amp: amp };
  }

  get audioLevel() { return this.audio.env; }

  // ---------------- frame ----------------
  update(dt) {
    this.time += dt;
    const p = this.p, t = this.t, k = this.controls, spd = k.speed;
    // transiciones de estado con resorte críticamente amortiguado (posición y velocidad continuas; 95 % en 3·tau)
    const w = 4.74 / (3 * this.tau), e = Math.exp(-w * dt);
    const spring = (x, goal, v) => { const x0 = x - goal, c = v + w * x0; return [goal + (x0 + c * dt) * e, (v - w * c * dt) * e]; };
    for (const key of NUM_KEYS) [p[key], this.v[key]] = spring(p[key], t[key], this.v[key]);
    for (const c of ["color", "color2", "bodyTint"]) {
      const C = this.col[c], T = this.colT[c], V = this.vCol[c];
      [C.r, V.x] = spring(C.r, T.r, V.x); [C.g, V.y] = spring(C.g, T.g, V.y); [C.b, V.z] = spring(C.b, T.b, V.z);
    }
    [this.bodyTintMix, this.vTintMix] = spring(this.bodyTintMix, t.bodyTintMix, this.vTintMix);

    // audio: nivel real con ataque/caída; sin datos recientes → 0
    const A = this.audio, fresh = this.time - A.rawT < AUDIO_STALE_S;
    const target = fresh ? A.raw : 0;
    A.env += (target - A.env) * (dt > 0 ? 1 - Math.exp(-dt / (target > A.env ? 0.03 : fresh ? 0.18 : 0.08)) : 0);
    if (!fresh && A.env < 1e-4) A.env = 0;
    A.slow += (A.env - A.slow) * (dt > 0 ? 1 - Math.exp(-dt / 0.35) : 0);
    if (A.env > 0.12 && A.env - A.slow > 0.07 && this.time - A.lastOnset > 0.14) {
      A.lastOnset = this.time; A.onsets++; this.stats.onsets++;
      if (this.state === "speaking") { this.spawnWave(1, 0.4 + A.env); if (A.env > 0.5) this.flash(CORE_PRESETS.speaking.color, 0.35); }
      else if (this.state === "listening") this.spawnWave(-1, 0.3 + A.env);
    }

    // fases acumuladas (la velocidad nunca provoca saltos)
    const ph = this.phase;
    ph.orbit += dt * p.orbitSpeed * spd; ph.flow += dt * 0.9 * spd; ph.noise += dt * p.noiseSpeed * spd; ph.ring += dt * p.ringSpeed * spd;
    ph.pulse += dt * p.pulseRate * spd; ph.swirl += dt * p.fieldSwirl * spd;
    const s = 0.5 + 0.5 * Math.sin(ph.pulse * 2 * Math.PI);
    const irr = 0.5 + 0.25 * Math.sin(ph.pulse * 2 * Math.PI) + 0.25 * Math.sin(ph.pulse * 2 * Math.PI * 2.37 + 1.3);
    const warn = Math.pow(Math.abs(Math.sin(ph.pulse * Math.PI)), 8);
    const wsum = Math.max(1e-3, p.pulseSine + p.pulseIrregular + p.pulseWarn);
    const shape = (p.pulseSine * s + p.pulseIrregular * irr + p.pulseWarn * warn) / wsum;
    const wA = Math.max(0, Math.min(1, p.pulseAudio));
    this.pulse = p.pulseAmp * (shape * (1 - 0.75 * wA) + wA * A.env * 1.3);

    // ondas automáticas del estado
    ph.waveAcc += dt * p.waveRate * spd;
    if (ph.waveAcc >= 1) { ph.waveAcc -= Math.floor(ph.waveAcc); if (p.waveRate > 0.05) this.spawnWave(p.waveDir >= 0 ? 1 : -1, 0.6); }

    // uniforms
    const pos = c => { c.r = Math.max(0, c.r); c.g = Math.max(0, c.g); c.b = Math.max(0, c.b); return c; };
    const U = this.U, col = pos((this._c1 ||= new THREE.Color()).copy(this.col.color)), col2 = pos((this._c2 ||= new THREE.Color()).copy(this.col.color2));
    if (k.color !== null && k.color !== undefined) {
      if (this._userHex !== k.color) { this._userHex = k.color; (this._userCol ||= new THREE.Color()).setHex(k.color, THREE.LinearSRGBColorSpace); }
      col.lerp(this._userCol, k.colorMix); col2.lerp(this._userCol, k.colorMix * 0.6);
    }
    U.uTime.value = this.time; U.uNoiseT.value = ph.noise; U.uOrbitPhase.value = ph.orbit; U.uFlowPhase.value = ph.flow;
    U.uPulse.value = this.pulse; U.uAudio.value = A.env; U.uAudioGain.value = p.audioGain; U.uTurb.value = p.turb; U.uFlow.value = p.flow;
    U.uIntensity.value = p.intensity * k.intensity; U.uBrightness.value = k.brightness; U.uScale.value = k.size;
    U.uColor.value.copy(col); U.uColor2.value.copy(col2);
    this.fieldU.uFieldSwirl.value = ph.swirl;
    this.rings.forEach((r, i) => {
      const d = r.userData; r.rotation.set(d.tilt[0] + Math.sin(ph.ring * 0.4 + i) * 0.15, ph.ring * d.k * d.dir, d.tilt[1]);
      r.material.uniforms.uRingPhase.value = ph.ring * (1.5 + i * 0.5) * d.dir; r.material.uniforms.uRingColor.value.copy(i === 1 ? col2 : col);
    });
    for (const w of this.waves) {
      if (!w.visible) continue;
      const d = w.userData; d.age += dt * Math.max(0.3, spd);
      const life = d.age / d.dur;
      if (life >= 1) { w.visible = false; continue; }
      const e = life * (2 - life);   // desaceleración
      w.material.uniforms.uR.value = (d.dir > 0 ? 0.06 + 0.55 * e : 0.6 - 0.54 * e) * k.size;
      w.material.uniforms.uA.value = p.waveAmp * k.waveAmplitude * d.amp * Math.sin(Math.PI * life) * (d.dir > 0 ? 1 - life : life) * 1.6 * k.brightness;
      w.material.uniforms.uC.value.copy(col);
    }
    for (const b of this.bursts) { if (!b.visible) continue; const u = b.material.uniforms.uAge; u.value += dt; if (u.value > 2.5) b.visible = false; }

    // posición del núcleo (sigue al pecho del esqueleto)
    if (this.anchorBone) { this.core.position.copy(this.anchorLocal).applyMatrix4(this.anchorBone.matrixWorld); }
    this.fieldU.uCore.value.copy(this.core.position);

    // integración con el cuerpo: tinte + onda de energía que recorre las partículas
    const B = this.bodyU;
    if (B) {
      B.uTint.value.copy(this.col.bodyTint); B.uTintMix.value = this.bodyTintMix * k.intensity;
      B.uEnergyOrigin.value.copy(this.core.position); B.uEnergyColor.value.copy(col);
      const bw = this.bodyWave;
      if (bw) { bw.r += dt * 1.5 * Math.max(0.3, spd); if (bw.r > 1.5) this.bodyWave = null; }
      B.uEnergyRadius.value = bw ? bw.r : 0;
      B.uEnergyAmp.value = bw ? p.bodyEnergy * bw.amp * (1 - bw.r / 1.5) * k.intensity * k.waveAmplitude : 0;
    }
  }

  setVisible(on) { this.object3D.visible = on; if (!on && this.bodyU) { this.bodyU.uEnergyAmp.value = 0; this.bodyU.uTintMix.value = 0; } }

  info() {
    return { state: this.state, counts: { ...this.counts }, ondasActivas: this.waves.filter(w => w.visible).length, rafagasActivas: this.bursts.filter(b => b.visible).length,
      audio: +this.audio.env.toFixed(3), pulso: +this.pulse.toFixed(3), ...this.stats };
  }

  dispose() {
    for (const g of this.geometries) g.dispose();
    for (const m of this.materials) m.dispose();
    this.object3D.removeFromParent();
    if (this.bodyU) { this.bodyU.uEnergyAmp.value = 0; this.bodyU.uTintMix.value = 0; }
    this.geometries = []; this.materials = [];
  }
}
