// ATLAS Fase 5C — controlador de animación del humanoide de partículas (GPU skinning).
//
// Fuente de movimiento: los 10 clips de cuerpo del GLB V004, sin recrearlos ni modificarlos. El mixer de Three.js
// sólo calcula los 73 huesos; las partículas se deforman en la GPU (ParticleEngine.computeSkin).
//
// Novedades frente a la 5B (la versión anterior se conserva en legacy/AnimationController5B.js):
//  · Pesos gestionados por el propio controlador, no por crossFadeTo de Three.js. crossFadeTo/fadeOut reinician
//    el peso del clip saliente a 1 (_scheduleFading(d, 1, 0)): si se cambia de clip a mitad de una transición,
//    el peso salta y la suma de pesos deja de ser 1 (la pose se mezcla con la de reposo). Aquí:
//      – cada instancia avanza su progreso lineal w ∈ [0,1] hacia su objetivo a ritmo 1/fade,
//      – se suaviza con smoothstep (sin cambio brusco de velocidad al empezar o acabar),
//      – y se NORMALIZA en cada frame: Σ pesos de cuerpo = 1 siempre.
//  · Instancias por clip (hasta 3 copias del mismo clip). Volver a un clip que aún se está desvaneciendo, o
//    repetir el clip actual, crea/reutiliza otra instancia en vez de reiniciar la que se ve: sin saltos.
//  · Reproducción/pausa, velocidad, bucle por clip, vuelta a Idle anticipada (el fundido empieza antes del final),
//    capas aditivas con máscara (p. ej. Nodding sobre Talking) y avance a un tiempo concreto.
//  · Los dedos de cada mano siguen el factor que fija HandGestureController (1 − Σ gestos de esa mano).
//  · 5D/5F: `baseClip` (por defecto Idle) es el clip de reposo al que vuelven stop() y los clips puntuales.
import * as THREE from "../../vendor/three.module.js";
import { BODY_CLIPS } from "../model/HumanoidParticleModel.js";

export const LOOPING = new Set(["Idle", "Talking", "Listening"]);
const MAX_INSTANCES = 3;
const isFinger = (bone, side) => new RegExp(`^DEF-(f_(index|middle|ring|pinky)|thumb)0[123]${side}$`).test(bone);
const isAnyFinger = bone => isFinger(bone, "L") || isFinger(bone, "R");
const trackBone = t => t.name.slice(0, t.name.lastIndexOf("."));
const smoothstep = x => x * x * (3 - 2 * x);
// máscaras para capas (nombres de hueso saneados por Three.js: sin puntos)
export const MASKS = {
  head: b => /^DEF-spine00[456]$/.test(b),
  upper: b => /^DEF-(spine00[3456]|shoulder|upper_arm|forearm|hand|shoulder_helper)/.test(b),
  full: () => true,
};

class ClipInstance {
  constructor(mixer, name, clip, k) {
    this.name = name; this.k = k; this.duration = clip.duration;
    const sub = (suffix, filter) => new THREE.AnimationClip(`${name}${suffix}#${k}`, clip.duration, clip.tracks.filter(filter));
    this.body = mixer.clipAction(sub("_sinDedos", t => !isAnyFinger(trackBone(t))));
    this.fingers = { L: mixer.clipAction(sub("_dedosL", t => isFinger(trackBone(t), "L"))), R: mixer.clipAction(sub("_dedosR", t => isFinger(trackBone(t), "R"))) };
    this.actions = [this.body, this.fingers.L, this.fingers.R];
    this.w = 0; this.target = 0; this.fade = 0.4; this._active = false; this.norm = 0;
  }
  /** Activa mientras la acción siga programada en el mixer (si alguien la detiene desde fuera, deja de contar). */
  get active() { return this._active && this.body.isScheduled(); }
  start(loop) {
    for (const a of this.actions) {
      a.reset(); a.setLoop(loop ? THREE.LoopRepeat : THREE.LoopOnce, Infinity); a.clampWhenFinished = !loop;
      a.enabled = true; a.setEffectiveWeight(0); a.play();
    }
    this._active = true; this.loop = loop;
  }
  stop() { for (const a of this.actions) a.stop(); this._active = false; this.w = 0; this.target = 0; this.norm = 0; }
  get time() { return this.body.time; }
  set time(t) { for (const a of this.actions) a.time = t; }
}

export class AnimationController extends EventTarget {
  constructor(model, { defaultFade = 0.5 } = {}) {
    super();
    this.model = model;
    this.mixer = new THREE.AnimationMixer(model.root);
    this.clips = new Map();
    for (const name of BODY_CLIPS) { const c = model.gltf.animations.find(a => a.name === name); if (c) this.clips.set(name, c); }
    this.pool = new Map([...this.clips.keys()].map(n => [n, []]));
    this.groups = new Map();              // compatibilidad 5B: instancia principal por clip (body / fingers / duration)
    for (const n of this.clips.keys()) this.groups.set(n, this._instance(n, 0));
    this.current = null;                  // instancia objetivo
    this.defaultFade = defaultFade;
    this.returnToIdle = true;
    this.idleFade = 0.5;
    this.baseClip = "Idle";               // 5D/5F: clip de reposo al que se vuelve (Idle, o Talking mientras habla, etc.)
    this.loopOverride = new Map();        // nombre → true/false (si no hay, LOOPING decide)
    this.speed = 1; this.paused = false;
    this.fingerFactor = { L: 1, R: 1 };
    this.layers = new Map();              // nombre → {inst, w, target, fade, mask}
    this.stats = { minWeightSum: 1, maxWeightSum: 1 };
  }

  _instance(name, k) {
    const list = this.pool.get(name);
    if (!list[k]) list[k] = new ClipInstance(this.mixer, name, this.clips.get(name), k);
    return list[k];
  }
  _free(name) {
    const list = this.pool.get(name);
    for (let k = 0; k < MAX_INSTANCES; k++) { const inst = this._instance(name, k); if (!inst.active) return inst; }
    return list.slice().sort((a, b) => a.norm - b.norm)[0];   // todas ocupadas: la de menor peso visible
  }

  get clipNames() { return [...this.clips.keys()]; }
  get currentName() { return this.current?.name ?? null; }
  get currentTime() { return this.current ? this.current.time : 0; }
  get currentDuration() { return this.current ? this.current.duration : 0; }
  isLooping(name) { return this.loopOverride.has(name) ? this.loopOverride.get(name) : LOOPING.has(name); }

  /**
   * Reproduce un clip de cuerpo con transición suave.
   * @param {string} name
   * @param {{fade?: number, restart?: boolean}} [o]  restart: si ya es el clip actual, vuelve a empezar (con fundido).
   */
  play(name, { fade = this.defaultFade, restart = false } = {}) {
    if (!this.clips.has(name)) throw new Error(`Clip de cuerpo desconocido: ${name}`);
    if (this.current && this.current.active && this.current.name === name && !restart) { this.current.target = 1; this.current.fade = fade; if (fade <= 0) this.current.w = 1; this._applyWeights(); return this.current; }
    // ¿una instancia de este clip que se está desvaneciendo? Si no se pide reinicio, se recupera tal cual (sin salto).
    let inst = null;
    if (!restart) inst = this.pool.get(name).find(i => i.active && i !== this.current);
    if (!inst) { inst = this._free(name); if (inst.active) inst.stop(); inst.start(this.isLooping(name)); }
    for (const list of this.pool.values()) for (const i of list) if (i.active) { i.target = 0; i.fade = fade; }
    inst.target = 1; inst.fade = fade;
    if (fade <= 0) for (const list of this.pool.values()) for (const i of list) if (i.active && i !== inst) i.stop();
    if (fade <= 0) inst.w = 1;
    this.current = inst;
    this._applyWeights();
    this.dispatchEvent(new CustomEvent("clip", { detail: name }));
    return inst;
  }

  /** Detener = volver a Idle con fundido (la pose nunca cae a la de reposo del rig). */
  stop({ fade = this.idleFade } = {}) { this.play(this.baseClip, { fade }); }
  /** 5F: cambia el clip de reposo y, si se pide, lo reproduce ya (con fundido). */
  setBaseClip(name, { play = true, fade = this.defaultFade } = {}) {
    if (!this.clips.has(name)) throw new Error(`Clip de cuerpo desconocido: ${name}`);
    this.baseClip = name;
    if (play) this.play(name, { fade });
  }
  pause() { this.paused = true; }
  resume() { this.paused = false; }
  setSpeed(s) { this.speed = Math.max(0, s); }
  setLoop(name, loop) {
    if (loop === null || loop === undefined) this.loopOverride.delete(name); else this.loopOverride.set(name, !!loop);
    for (const i of this.pool.get(name) || []) if (i.active) for (const a of i.actions) { a.setLoop(this.isLooping(name) ? THREE.LoopRepeat : THREE.LoopOnce, Infinity); a.clampWhenFinished = !this.isLooping(name); }
  }

  /**
   * Capa aditiva (o de sustitución) encima del clip actual, p. ej. setLayer("Nodding", 0.8, {mask: "head"}).
   * Aditiva respecto a su primer frame; nunca toca los dedos (son de HandGestureController).
   */
  setLayer(name, weight, { mask = "head", fade = 0.3, additive = true } = {}) {
    if (!this.clips.has(name)) throw new Error(`Clip desconocido: ${name}`);
    let L = this.layers.get(name);
    if (!L || L.mask !== mask || L.additive !== additive) {
      if (L) L.action.stop();
      const src = this.clips.get(name), m = MASKS[mask] || MASKS.head;
      let clip = new THREE.AnimationClip(`${name}_capa_${mask}`, src.duration, src.tracks.filter(t => !isAnyFinger(trackBone(t)) && m(trackBone(t))).map(t => t.clone()));
      if (additive) clip = THREE.AnimationUtils.makeClipAdditive(clip, 0);
      const action = this.mixer.clipAction(clip);
      action.setLoop(THREE.LoopRepeat, Infinity); action.setEffectiveWeight(0); action.play();
      L = { name, action, w: 0, target: 0, fade, mask, additive };
      this.layers.set(name, L);
    }
    L.target = Math.max(0, Math.min(1, weight)); L.fade = fade;
  }
  clearLayer(name, { fade = 0.3 } = {}) { const L = this.layers.get(name); if (L) { L.target = 0; L.fade = fade; } }

  /** Factor de los dedos del clip de cuerpo para una mano (lo fija HandGestureController). */
  setFingerFactor(side, f) { this.fingerFactor[side] = f; }

  _advanceWeights(dt) {
    for (const list of this.pool.values()) for (const i of list) {
      if (!i.active) continue;
      if (i.fade <= 0) i.w = i.target;
      else i.w = Math.max(0, Math.min(1, i.w + Math.sign(i.target - i.w) * dt / i.fade));
      if (i.w === 0 && i.target === 0) i.stop();
    }
    for (const L of this.layers.values()) {
      L.w = L.fade <= 0 ? L.target : L.w + Math.sign(L.target - L.w) * Math.min(Math.abs(L.target - L.w), dt / L.fade);
    }
    // vuelta a Idle anticipada: el fundido termina justo al acabar el clip (sin quedarse congelado)
    const c = this.current;
    if (c && !c.loop && this.returnToIdle && c.name !== this.baseClip && c.time >= c.duration - this.idleFade - 1e-6) {
      this.dispatchEvent(new CustomEvent("finished", { detail: c.name }));
      this.play(this.baseClip, { fade: Math.max(0.05, Math.min(this.idleFade, c.duration - c.time)) });
    }
  }

  _applyWeights() {
    let sum = 0;
    for (const list of this.pool.values()) for (const i of list) if (i.active) { i.s = smoothstep(i.w); sum += i.s; }
    if (sum <= 0 && this.current) { this.current.s = 1; sum = 1; }
    for (const list of this.pool.values()) for (const i of list) {
      if (!i.active) continue;
      i.norm = i.s / sum;
      i.body.setEffectiveWeight(i.norm);
      i.fingers.L.setEffectiveWeight(i.norm * this.fingerFactor.L);
      i.fingers.R.setEffectiveWeight(i.norm * this.fingerFactor.R);
    }
    for (const L of this.layers.values()) L.action.setEffectiveWeight(smoothstep(Math.max(0, Math.min(1, L.w))));
    let total = 0; for (const list of this.pool.values()) for (const i of list) if (i.active) total += i.norm;
    this.stats.lastWeightSum = total;
    this.stats.minWeightSum = Math.min(this.stats.minWeightSum, total);
    this.stats.maxWeightSum = Math.max(this.stats.maxWeightSum, total);
  }

  /** Avance normal por frame. */
  update(dt) {
    const d = this.paused ? 0 : dt * this.speed;      // tiempo del clip (velocidad)
    this._advanceWeights(this.paused ? 0 : dt);       // los fundidos van en tiempo real
    this._applyWeights();
    this.mixer.update(d);
  }

  /** Lleva el clip actual a un tiempo (s) y deja sólo esa instancia (pruebas y barra de tiempo). */
  setTime(t) {
    const c = this.current;
    if (!c) return;
    for (const list of this.pool.values()) for (const i of list) if (i.active && i !== c) i.stop();
    c.w = 1; c.target = 1;
    this._applyWeights();
    c.time = Math.max(0, Math.min(t, c.loop ? t : c.duration));
    this.mixer.update(0);
  }

  /** Instancias con peso (diagnóstico). */
  activeInstances() { const out = []; for (const list of this.pool.values()) for (const i of list) if (i.active) out.push({ name: i.name, k: i.k, w: +i.w.toFixed(3), peso: +i.norm.toFixed(3), t: +i.time.toFixed(3) }); return out; }
  /** Compatibilidad 5B. */
  activeGroups() { const out = []; for (const list of this.pool.values()) for (const i of list) if (i.active) out.push(i); return out; }
  get actionCount() { return this.mixer._actions.length; }

  dispose() { this.mixer.stopAllAction(); this.mixer.uncacheRoot(this.model.root); this.layers.clear(); }
}
