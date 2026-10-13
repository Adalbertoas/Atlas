import { Canvas, useFrame, useLoader } from "@react-three/fiber";
import { Suspense, useMemo, useRef } from "react";
import { GLTFLoader } from "three/examples/jsm/loaders/GLTFLoader.js";
import * as THREE from "three";

export type AvatarState = "idle" | "listening" | "thinking" | "speaking";

function AvatarMotion({ state, children }: { state: AvatarState; children: React.ReactNode }) {
  const group = useRef<THREE.Group>(null!);
  useFrame((frame, delta) => {
    const energy = state === "listening" ? 1.18 : state === "speaking" ? 1.10 : state === "thinking" ? 1.06 : 1;
    group.current.rotation.y += delta * (state === "thinking" ? 0.26 : 0.10);
    group.current.position.y = Math.sin(frame.clock.elapsedTime * 1.4) * 0.045;
    group.current.scale.setScalar(energy);
  });
  return <group ref={group}>{children}</group>;
}

function ProceduralFallback({ state }: { state: AvatarState }) {
  const points = useMemo(() => {
    const data: number[] = [];
    for (let i = 0; i < 9000; i += 1) {
      const r = Math.random(); let x = 0; let y = 0; let z = 0;
      if (r < 0.26) { const u = Math.random() * 2 - 1; const angle = Math.random() * Math.PI * 2; const radius = 0.58 * Math.cbrt(Math.random()); x = radius * Math.sqrt(1 - u * u) * Math.cos(angle); y = 1.72 + radius * u; z = radius * Math.sqrt(1 - u * u) * Math.sin(angle); }
      else if (r < 0.83) { const t = Math.random(); const angle = (Math.random() - 0.5) * 2.2; y = 1.18 - t * 1.65; const width = 0.62 * (1 - t) + 0.18; x = Math.sin(angle) * width * (1 - t * 0.3); z = (Math.random() - 0.5) * 0.38; }
      else { const side = Math.random() < 0.5 ? -1 : 1; const t = Math.random(); x = side * (0.42 + t * 0.7); y = 1.25 - t * 1.55; z = (Math.random() - 0.5) * 0.25; }
      data.push(x, y, z);
    }
    return new Float32Array(data);
  }, []);
  return <AvatarMotion state={state}><points><bufferGeometry><bufferAttribute attach="attributes-position" args={[points, 3]} /></bufferGeometry><pointsMaterial color="#52dfff" size={0.017} transparent opacity={0.82} depthWrite={false} /></points></AvatarMotion>;
}

function BlenderPointAvatar({ state }: { state: AvatarState }) {
  const gltf = useLoader(GLTFLoader, "./models/atlas-humanoid.glb"); // relativa: con file:// una ruta "/models" apunta a la raíz del disco
  const geometry = useMemo(() => {
    const positions: number[] = [];
    gltf.scene.updateMatrixWorld(true);
    gltf.scene.traverse((object) => {
      if (!(object instanceof THREE.Mesh)) return;
      const attribute = object.geometry.getAttribute("position");
      const vertex = new THREE.Vector3();
      for (let index = 0; index < attribute.count; index += 1) {
        vertex.fromBufferAttribute(attribute, index).applyMatrix4(object.matrixWorld);
        positions.push(vertex.x, vertex.y, vertex.z);
      }
    });
    const result = new THREE.BufferGeometry();
    result.setAttribute("position", new THREE.Float32BufferAttribute(positions, 3));
    return result;
  }, [gltf]);

  const color = state === "thinking" ? "#a6b7ff" : state === "speaking" ? "#a4fbff" : "#52dfff";
  return <AvatarMotion state={state}>
    <points geometry={geometry}><pointsMaterial color={color} size={0.019} transparent opacity={0.88} depthWrite={false} sizeAttenuation /></points>
    <mesh position={[0, 0.02, -0.36]}><circleGeometry args={[0.34, 48]} /><meshBasicMaterial color="#60dcff" transparent opacity={0.10} /></mesh>
    <pointLight color="#39d7ff" intensity={state === "speaking" ? 4 : 2} distance={5} />
  </AvatarMotion>;
}

function Rings() {
  const ring = useRef<THREE.Group>(null!);
  useFrame((_frame, delta) => { ring.current.rotation.z += delta * 0.13; });
  return <group ref={ring} rotation={[Math.PI / 2, 0, 0]}>{[1.0, 1.25, 1.55].map((radius, index) => <mesh key={radius} rotation={[0, 0, index * 0.4]}><torusGeometry args={[radius, 0.008, 8, 96]} /><meshBasicMaterial color="#39cfff" transparent opacity={0.45 - index * 0.1} /></mesh>)}</group>;
}

export function Hologram({ state, paused = false }: { state: AvatarState; paused?: boolean }) {
  return <Canvas dpr={[1, 1.5]} frameloop={paused ? "never" : "always"} camera={{ position: [0, 0.45, 4.4], fov: 42 }} gl={{ powerPreference: "high-performance", alpha: true }}>
    <ambientLight intensity={0.25} />
    <Suspense fallback={<ProceduralFallback state={state} />}><BlenderPointAvatar state={state} /></Suspense>
    <Rings />
  </Canvas>;
}