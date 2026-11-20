// [CONSERVADO SIN CAMBIOS DE LÓGICA — versión de la Fase 5B, sólo para pruebas comparativas]
// ATLAS Fase 5B — reproducción de los clips de cuerpo del GLB (sin recrearlos).
// Cada clip de cuerpo se separa al cargar en tres sub-clips: "sin dedos", "dedos izq." y "dedos der.".
// Así HandGestureController puede sustituir los dedos de una mano por un gesto (patrón validado en la Fase 4)
// mientras el resto del cuerpo sigue la animación. Los crossfades mueven los tres sub-clips a la vez.
import * as THREE from "../../../vendor/three.module.js";
import { BODY_CLIPS } from "../../model/HumanoidParticleModel.js";

export const LOOPING = new Set(["Idle", "Talking", "Listening"]);
const isFinger = (bone, side) => new RegExp(`^DEF-(f_(index|middle|ring|pinky)|thumb)0[123]${side}$`).test(bone);
const trackBone = t => t.name.slice(0, t.name.lastIndexOf("."));

export class AnimationController5B extends EventTarget {
  constructor(model) {
    super();
    this.model = model;
    this.mixer = new THREE.AnimationMixer(model.root);
    this.groups = new Map();   // nombre → {body, fingers:{L,R}}
    for (const name of BODY_CLIPS) {
      const clip = model.gltf.animations.find(a => a.name === name);
      if (!clip) continue;
      const sub = (suffix, filter) => new THREE.AnimationClip(`${name}${suffix}`, clip.duration, clip.tracks.filter(filter));
      const body = this.mixer.clipAction(sub("_sinDedos", t => !isFinger(trackBone(t), "L") && !isFinger(trackBone(t), "R")));
      const L = this.mixer.clipAction(sub("_dedosL", t => isFinger(trackBone(t), "L")));
      const R = this.mixer.clipAction(sub("_dedosR", t => isFinger(trackBone(t), "R")));
      this.groups.set(name, { name, body, fingers: { L, R }, duration: clip.duration });
    }
    this.current = null;
    this.returnToIdle = true;
    this.mixer.addEventListener("finished", e => {
      const g = this.current;
      if (g && e.action === g.body && !LOOPING.has(g.name) && this.returnToIdle) this.play("Idle");
    });
  }

  get clipNames() { return [...this.groups.keys()]; }

  /** Reproduce un clip de cuerpo con crossfade (segundos). */
  play(name, { fade = 0.4 } = {}) {
    const next = this.groups.get(name);
    if (!next) throw new Error(`Clip de cuerpo desconocido: ${name}`);
    const prev = this.current;
    const loop = LOOPING.has(name) ? THREE.LoopRepeat : THREE.LoopOnce;
    for (const a of [next.body, next.fingers.L, next.fingers.R]) {
      a.reset(); a.setLoop(loop, Infinity); a.clampWhenFinished = !LOOPING.has(name); a.enabled = true; a.setEffectiveWeight(1); a.play();
    }
    if (prev && prev !== next && fade > 0) {
      prev.body.crossFadeTo(next.body, fade, false);
      prev.fingers.L.crossFadeTo(next.fingers.L, fade, false);
      prev.fingers.R.crossFadeTo(next.fingers.R, fade, false);
    } else if (prev && prev !== next) {
      for (const a of [prev.body, prev.fingers.L, prev.fingers.R]) a.stop();
    }
    this.current = next;
    this.dispatchEvent(new CustomEvent("clip", { detail: name }));
  }

  /** Grupos con peso (para que el control de gestos ajuste los dedos de todos los clips activos). */
  activeGroups() { return [...this.groups.values()].filter(g => g.body.isRunning() || g.body.getEffectiveWeight() > 0); }

  update(dt) { this.mixer.update(dt); }

  /** Coloca el clip actual en un tiempo concreto (pruebas). */
  setTime(t) {
    for (const g of this.groups.values()) for (const a of [g.body, g.fingers.L, g.fingers.R]) a.time = 0;
    this.mixer.setTime(t);
  }

  dispose() { this.mixer.stopAllAction(); this.mixer.uncacheRoot(this.model.root); }
}
