import * as THREE from "three";
import type { CoreFrame } from "./ParticleAnimator.ts";
import type { QualityProfile } from "./ParticlePresets.ts";
import { particleFragmentShader, particleVertexShader } from "./ParticleShaders.ts";

export function createParticleMaterial(profile: QualityProfile): THREE.ShaderMaterial {
  return new THREE.ShaderMaterial({
    vertexShader: particleVertexShader,
    fragmentShader: particleFragmentShader,
    defines: profile.simplexNoise ? { USE_SIMPLEX: "" } : {},
    uniforms: {
      uTime: { value: 0 },
      uExpansion: { value: 1 },
      uRotation: { value: new THREE.Vector3() },
      uGestureStrength: { value: 0 },
      uAudioLevel: { value: 0 },
      uAudioBass: { value: 0 },
      uAudioMid: { value: 0 },
      uAudioTreble: { value: 0 },
      uEmotion: { value: 0 },
      uInteractionPoint: { value: new THREE.Vector3() },
      uInteractionStrength: { value: 0 },
      uExplosionProgress: { value: 0 },
      uPulse: { value: -1 },
      uRing: { value: 0 },
      uCloud: { value: 0 },
      uVortex: { value: 0 },
      uVortexPhase: { value: 0 },
      uWavePhase: { value: 0 },
      uWaveStrength: { value: 0 },
      uJitter: { value: 0 },
      uSize: { value: 0.03 },
      uScale: { value: 600 },
      uColorA: { value: new THREE.Color() },
      uColorB: { value: new THREE.Color() },
      uBrightness: { value: 1 },
    },
    transparent: true,
    depthWrite: false,
    depthTest: false,
    blending: THREE.AdditiveBlending,
  });
}

export function applyFrame(material: THREE.ShaderMaterial, frame: CoreFrame): void {
  const u = material.uniforms;
  u.uTime.value = frame.time;
  u.uExpansion.value = frame.expansion;
  (u.uRotation.value as THREE.Vector3).set(frame.yaw, frame.pitch, frame.roll);
  u.uGestureStrength.value = frame.gestureStrength;
  u.uAudioLevel.value = frame.audio.level;
  u.uAudioBass.value = frame.audio.bass;
  u.uAudioMid.value = frame.audio.mid;
  u.uAudioTreble.value = frame.audio.treble;
  u.uEmotion.value = frame.emotion;
  (u.uInteractionPoint.value as THREE.Vector3).fromArray(frame.interaction);
  u.uInteractionStrength.value = frame.interactionStrength;
  u.uExplosionProgress.value = frame.explosion;
  u.uPulse.value = frame.pulse;
  u.uRing.value = frame.ring;
  u.uCloud.value = frame.cloud;
  u.uVortex.value = frame.vortex;
  u.uVortexPhase.value = frame.vortexPhase;
  u.uWavePhase.value = frame.wavePhase;
  u.uWaveStrength.value = frame.waveStrength;
  u.uJitter.value = frame.jitter;
  u.uSize.value = frame.size;
  (u.uColorA.value as THREE.Color).setRGB(frame.colorA[0], frame.colorA[1], frame.colorA[2]);
  (u.uColorB.value as THREE.Color).setRGB(frame.colorB[0], frame.colorB[1], frame.colorB[2]);
  u.uBrightness.value = frame.brightness;
}
