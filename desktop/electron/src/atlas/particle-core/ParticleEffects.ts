import * as THREE from "three";
import { haloFragmentShader, haloVertexShader } from "./ParticleShaders.ts";

/** Halo luminoso: un único quad aditivo. Es lo que da el resplandor en todas las
    calidades, así el núcleo no depende del bloom para verse bien. */
export class Halo {
  readonly mesh: THREE.Mesh;
  private readonly material: THREE.ShaderMaterial;
  private readonly geometry: THREE.PlaneGeometry;

  constructor() {
    this.geometry = new THREE.PlaneGeometry(5, 5);
    this.material = new THREE.ShaderMaterial({
      vertexShader: haloVertexShader,
      fragmentShader: haloFragmentShader,
      uniforms: { uColor: { value: new THREE.Color() }, uIntensity: { value: 0.3 } },
      transparent: true,
      depthWrite: false,
      depthTest: false,
      blending: THREE.AdditiveBlending,
    });
    this.mesh = new THREE.Mesh(this.geometry, this.material);
    this.mesh.renderOrder = -1;
  }

  update(color: readonly [number, number, number], intensity: number): void {
    (this.material.uniforms.uColor.value as THREE.Color).setRGB(color[0], color[1], color[2]);
    this.material.uniforms.uIntensity.value = intensity;
  }

  dispose(): void {
    this.geometry.dispose();
    this.material.dispose();
  }
}

export type BloomPipeline = {
  render(): void;
  setSize(width: number, height: number, pixelRatio: number): void;
  dispose(): void;
};

/** Bloom opcional (solo HIGH). Los pases de posprocesado se cargan bajo demanda
    para que no pesen en el arranque ni en las calidades que no los usan. */
export async function createBloomPipeline(renderer: THREE.WebGLRenderer, scene: THREE.Scene, camera: THREE.Camera): Promise<BloomPipeline> {
  if (!renderer.capabilities.isWebGL2) throw new Error("El bloom requiere WebGL2.");
  const [{ EffectComposer }, { RenderPass }, { UnrealBloomPass }, { OutputPass }] = await Promise.all([
    import("three/examples/jsm/postprocessing/EffectComposer.js"),
    import("three/examples/jsm/postprocessing/RenderPass.js"),
    import("three/examples/jsm/postprocessing/UnrealBloomPass.js"),
    import("three/examples/jsm/postprocessing/OutputPass.js"),
  ]);
  const size = renderer.getSize(new THREE.Vector2());
  const composer = new EffectComposer(renderer);
  composer.addPass(new RenderPass(scene, camera));
  const bloom = new UnrealBloomPass(size.clone().multiplyScalar(0.5), 0.55, 0.6, 0.2);
  composer.addPass(bloom);
  composer.addPass(new OutputPass());
  return {
    render: () => composer.render(),
    setSize: (width, height, pixelRatio) => {
      composer.setPixelRatio(pixelRatio);
      composer.setSize(width, height);
    },
    dispose: () => {
      bloom.dispose();
      composer.dispose();
    },
  };
}
