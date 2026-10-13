import * as THREE from "three";
import { buildParticleData } from "./ParticleData.ts";

/** Un único BufferGeometry con todos los atributos: una sola llamada de dibujo. */
export function createParticleGeometry(count: number): THREE.BufferGeometry {
  const data = buildParticleData(count);
  const geometry = new THREE.BufferGeometry();
  geometry.setAttribute("position", new THREE.BufferAttribute(data.sphere, 3));
  geometry.setAttribute("aRing", new THREE.BufferAttribute(data.ring, 3));
  geometry.setAttribute("aCloud", new THREE.BufferAttribute(data.cloud, 3));
  geometry.setAttribute("aSeed", new THREE.BufferAttribute(data.seed, 4));
  geometry.setAttribute("aSize", new THREE.BufferAttribute(data.size, 1));
  // Los vértices se desplazan en el shader (explosión incluida): un bounding
  // sphere fijo y amplio evita recalcularlo y que el frustum culling los recorte.
  geometry.boundingSphere = new THREE.Sphere(new THREE.Vector3(), 12);
  return geometry;
}
