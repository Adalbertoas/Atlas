// Generación determinista de los atributos por partícula. Módulo puro.

export type ParticleData = {
  count: number;
  /** Forma base: esfera volumétrica de radio ~1. */
  sphere: Float32Array;
  ring: Float32Array;
  cloud: Float32Array;
  /** Cuatro valores aleatorios [0,1) por partícula para desfasar la animación. */
  seed: Float32Array;
  size: Float32Array;
};

function mulberry32(seed: number): () => number {
  let state = seed >>> 0;
  return () => {
    state = (state + 0x6d2b79f5) >>> 0;
    let t = state;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

function gaussian(random: () => number): number {
  const u = Math.max(random(), 1e-9);
  return Math.sqrt(-2 * Math.log(u)) * Math.cos(2 * Math.PI * random());
}

export function buildParticleData(count: number, seedValue = 1337): ParticleData {
  const random = mulberry32(seedValue);
  const sphere = new Float32Array(count * 3);
  const ring = new Float32Array(count * 3);
  const cloud = new Float32Array(count * 3);
  const seed = new Float32Array(count * 4);
  const size = new Float32Array(count);

  for (let i = 0; i < count; i += 1) {
    const i3 = i * 3;

    // Esfera: dirección uniforme; el 70 % forma una corteza y el resto rellena
    // el interior para que tenga volumen real y no parezca una cáscara hueca.
    const u = random() * 2 - 1;
    const theta = random() * Math.PI * 2;
    const flat = Math.sqrt(1 - u * u);
    const radius = random() < 0.7 ? 0.82 + random() * 0.18 : 0.15 + 0.67 * Math.cbrt(random());
    sphere[i3] = flat * Math.cos(theta) * radius;
    sphere[i3 + 1] = u * radius;
    sphere[i3 + 2] = flat * Math.sin(theta) * radius;

    // Anillo: toro fino en el plano XZ con sección gaussiana.
    const ringAngle = random() * Math.PI * 2;
    const ringRadius = 1.15 + gaussian(random) * 0.06;
    ring[i3] = Math.cos(ringAngle) * ringRadius;
    ring[i3 + 1] = gaussian(random) * 0.05;
    ring[i3 + 2] = Math.sin(ringAngle) * ringRadius;

    // Nube: masa gaussiana achatada, sin borde definido.
    cloud[i3] = gaussian(random) * 0.85;
    cloud[i3 + 1] = gaussian(random) * 0.5;
    cloud[i3 + 2] = gaussian(random) * 0.85;

    seed[i * 4] = random();
    seed[i * 4 + 1] = random();
    seed[i * 4 + 2] = random();
    seed[i * 4 + 3] = random();

    // Mayoría de partículas pequeñas y unas pocas grandes que dan destellos.
    size[i] = random() < 0.06 ? 1.8 + random() * 1.2 : 0.55 + random() * 0.75;
  }

  return { count, sphere, ring, cloud, seed, size };
}
