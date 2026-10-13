import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { damp, NO_GESTURE, ParticleAnimator, SILENCE, type CoreInputs } from "./ParticleAnimator.ts";
import { buildParticleData } from "./ParticleData.ts";
import { hexToRgb, nextLowerQuality, pickInitialQuality, QUALITY_PROFILES, VISUAL_PRESETS, type PresetName } from "./ParticlePresets.ts";
import { PerformanceMonitor } from "./PerformanceMonitor.ts";

const DT = 1 / 60;
const inputs = (patch: Partial<CoreInputs> = {}): CoreInputs => ({ preset: VISUAL_PRESETS.idle, gesture: NO_GESTURE, audio: SILENCE, intensity: 0.75, energyEffects: true, motionScale: 1, tint: null, ...patch });
const run = (animator: ParticleAnimator, seconds: number, input: CoreInputs) => {
  let frame = animator.step(DT, input);
  for (let t = DT; t < seconds; t += DT) frame = animator.step(DT, input);
  return frame;
};

describe("configuración de calidad", () => {
  it("cada nivel respeta su rango de partículas", () => {
    const low = QUALITY_PROFILES.low.particleCount;
    const medium = QUALITY_PROFILES.medium.particleCount;
    const high = QUALITY_PROFILES.high.particleCount;
    assert.ok(low >= 1500 && low <= 3000);
    assert.ok(medium >= 4000 && medium <= 7000);
    assert.ok(high >= 8000 && high <= 15000);
  });

  it("solo la calidad alta permite bloom y LOW usa el shader reducido", () => {
    assert.equal(QUALITY_PROFILES.low.bloomAllowed, false);
    assert.equal(QUALITY_PROFILES.medium.bloomAllowed, false);
    assert.equal(QUALITY_PROFILES.high.bloomAllowed, true);
    assert.equal(QUALITY_PROFILES.low.simplexNoise, false);
    assert.equal(QUALITY_PROFILES.low.maxPixelRatio, 1);
  });

  it("baja de nivel de uno en uno hasta LOW", () => {
    assert.equal(nextLowerQuality("high"), "medium");
    assert.equal(nextLowerQuality("medium"), "low");
    assert.equal(nextLowerQuality("low"), null);
  });

  it("el modo automático nunca arranca en HIGH y usa LOW con render por software", () => {
    assert.equal(pickInitialQuality("ANGLE (Intel, Intel(R) UHD Graphics 630 Direct3D11)"), "medium");
    assert.equal(pickInitialQuality("ANGLE (NVIDIA, NVIDIA GeForce RTX 4090 Direct3D11)"), "medium");
    assert.equal(pickInitialQuality("Google SwiftShader"), "low");
    assert.equal(pickInitialQuality(null), "medium");
  });

  it("hay un preset para cada estado visual", () => {
    const names: PresetName[] = ["idle", "listening", "thinking", "speaking", "processing", "success", "error", "sleeping"];
    for (const name of names) assert.ok(VISUAL_PRESETS[name], name);
    assert.ok(VISUAL_PRESETS.listening.waveDirection < 0, "ondas entrantes al escuchar");
    assert.ok(VISUAL_PRESETS.speaking.waveDirection > 0, "ondas salientes al hablar");
    assert.ok(VISUAL_PRESETS.processing.timeScale > VISUAL_PRESETS.idle.timeScale);
    assert.ok(VISUAL_PRESETS.sleeping.timeScale < VISUAL_PRESETS.idle.timeScale);
    assert.ok(VISUAL_PRESETS.error.jitter > 0);
  });

  it("convierte colores hexadecimales", () => {
    assert.deepEqual(hexToRgb("#ff0000"), [1, 0, 0]);
    assert.deepEqual(hexToRgb("00FF00"), [0, 1, 0]);
    assert.equal(hexToRgb("rojo"), null);
  });
});

describe("buildParticleData", () => {
  it("genera todos los atributos con el tamaño correcto", () => {
    const data = buildParticleData(500);
    assert.equal(data.sphere.length, 1500);
    assert.equal(data.ring.length, 1500);
    assert.equal(data.cloud.length, 1500);
    assert.equal(data.seed.length, 2000);
    assert.equal(data.size.length, 500);
  });

  it("la esfera es volumétrica: radio <= 1 con partículas en el interior", () => {
    const data = buildParticleData(4000);
    let inside = 0;
    for (let i = 0; i < data.count; i += 1) {
      const radius = Math.hypot(data.sphere[i * 3], data.sphere[i * 3 + 1], data.sphere[i * 3 + 2]);
      assert.ok(radius <= 1.0001);
      if (radius < 0.8) inside += 1;
    }
    assert.ok(inside > data.count * 0.15 && inside < data.count * 0.45, `interior: ${inside}`);
  });

  it("es determinista y no produce valores inválidos", () => {
    const a = buildParticleData(300);
    const b = buildParticleData(300);
    assert.deepEqual(a.sphere, b.sphere);
    for (const array of [a.sphere, a.ring, a.cloud, a.seed, a.size]) assert.ok(array.every(Number.isFinite));
  });
});

describe("ParticleAnimator", () => {
  it("damp no depende de la tasa de fotogramas", () => {
    let fine = 0;
    for (let i = 0; i < 10; i += 1) fine = damp(fine, 1, 4, 0.01);
    assert.ok(Math.abs(fine - damp(0, 1, 4, 0.1)) < 1e-12);
  });

  it("un cambio de estado no produce saltos de color, expansión ni forma", () => {
    const animator = new ParticleAnimator();
    let previous = { ...run(animator, 2, inputs()), colorA: [...animator.step(DT, inputs()).colorA] };
    for (const name of ["error", "thinking", "processing", "sleeping", "speaking"] as PresetName[]) {
      for (let i = 0; i < 30; i += 1) {
        const frame = animator.step(DT, inputs({ preset: VISUAL_PRESETS[name] }));
        for (let c = 0; c < 3; c += 1) assert.ok(Math.abs(frame.colorA[c] - previous.colorA[c]) < 0.06, `${name}: salto de color`);
        assert.ok(Math.abs(frame.expansion - previous.expansion) < 0.03, `${name}: salto de expansión`);
        assert.ok(Math.abs(frame.cloud - previous.cloud) < 0.03, `${name}: salto de forma`);
        assert.ok(Math.abs(frame.brightness - previous.brightness) < 0.06, `${name}: salto de brillo`);
        previous = { ...frame, colorA: [...frame.colorA] };
      }
    }
  });

  it("acaba convergiendo al preset del estado", () => {
    const animator = new ParticleAnimator();
    const frame = run(animator, 6, inputs({ preset: VISUAL_PRESETS.thinking }));
    assert.ok(Math.abs(frame.cloud - VISUAL_PRESETS.thinking.cloud) < 0.01);
    assert.ok(Math.abs(frame.colorA[0] - VISUAL_PRESETS.thinking.colorA[0]) < 0.01);
  });

  it("la explosión dispersa y luego se reconstruye sola por completo", () => {
    const animator = new ParticleAnimator();
    run(animator, 1, inputs());
    animator.triggerExplosion();
    assert.ok(run(animator, 0.6, inputs()).explosion > 0.9);
    assert.equal(run(animator, 6, inputs()).explosion, 0, "vuelve exactamente a la esfera");
    assert.equal(animator.exploding, false);
  });

  it("la reconstrucción es reversible desde cualquier punto y sin saltos", () => {
    const animator = new ParticleAnimator();
    animator.triggerExplosion();
    let previous = run(animator, 0.15, inputs()).explosion;
    assert.ok(previous > 0.2 && previous < 0.95);
    animator.reconstruct();
    for (let i = 0; i < 240; i += 1) {
      const value = animator.step(DT, inputs()).explosion;
      assert.ok(value <= previous + 1e-9, "decrece de forma monótona");
      assert.ok(previous - value < 0.05, "sin saltos");
      previous = value;
    }
    assert.ok(previous < 0.01);
  });

  it("el pulso de energía avanza y termina", () => {
    const animator = new ParticleAnimator();
    assert.equal(animator.step(DT, inputs()).pulse, -1);
    animator.triggerPulse();
    const mid = run(animator, 0.5, inputs()).pulse;
    assert.ok(mid > 0.3 && mid < 0.7);
    assert.equal(run(animator, 1, inputs()).pulse, -1);
  });

  it("los gestos expanden, contraen y rotan dentro de límites", () => {
    const open = run(new ParticleAnimator(), 3, inputs({ gesture: { ...NO_GESTURE, strength: 1, expansion: 1 } }));
    const fist = run(new ParticleAnimator(), 3, inputs({ gesture: { ...NO_GESTURE, strength: 1, expansion: -1 } }));
    assert.ok(open.expansion > 1.3 && open.expansion <= 1.7);
    assert.ok(fist.expansion < 0.7 && fist.expansion >= 0.45);

    const still = inputs({ preset: { ...VISUAL_PRESETS.idle, rotationSpeed: 0 } });
    const turned = run(new ParticleAnimator(), 3, { ...still, gesture: { ...NO_GESTURE, strength: 1, yaw: 0.8, pitch: -0.4 } });
    const rest = run(new ParticleAnimator(), 3, still);
    assert.ok(Math.abs(turned.yaw - 0.8) < 0.01);
    assert.ok(Math.abs(turned.pitch - rest.pitch + 0.4) < 0.01);
  });

  it("sin seguimiento (strength 0) los gestos no influyen", () => {
    const frame = run(new ParticleAnimator(), 3, inputs({ gesture: { ...NO_GESTURE, strength: 0, expansion: 1, yaw: 1, pitch: 1, vortex: 1, interaction: [1, 1] } }));
    const baseline = run(new ParticleAnimator(), 3, inputs());
    assert.ok(Math.abs(frame.expansion - baseline.expansion) < 1e-9);
    assert.ok(Math.abs(frame.vortex) < 1e-9);
    assert.ok(Math.abs(frame.interactionStrength) < 1e-9);
  });

  it("el volumen de la voz expande y aumenta el brillo", () => {
    const quiet = run(new ParticleAnimator(), 2, inputs());
    const loud = run(new ParticleAnimator(), 2, inputs({ audio: { level: 1, bass: 1, mid: 1, treble: 1 } }));
    assert.ok(loud.expansion > quiet.expansion);
    assert.ok(loud.brightness > quiet.brightness);
    assert.equal(loud.audio.bass, 1);
  });

  it("respeta 'Animaciones' desactivadas y 'Efectos de energía' desactivados", () => {
    const frozen = run(new ParticleAnimator(), 3, inputs({ motionScale: 0 }));
    assert.ok(Math.abs(frozen.yaw) < 1e-6, "sin giro automático");
    const plain = run(new ParticleAnimator(), 3, inputs({ energyEffects: false, preset: VISUAL_PRESETS.speaking }));
    assert.ok(plain.waveStrength < 1e-3);
    assert.ok(plain.halo < 1e-3);
  });

  it("un color personalizado sustituye al del preset", () => {
    const frame = run(new ParticleAnimator(), 4, inputs({ tint: [1, 0, 0] }));
    assert.ok(frame.colorA[0] > 0.98 && frame.colorA[1] < 0.02);
  });
});

describe("PerformanceMonitor", () => {
  const options = { minFps: 42, sustainMs: 4000, cooldownMs: 8000 };
  const feed = (monitor: PerformanceMonitor, from: number, durationMs: number, frameMs: number) => {
    let fired = 0;
    let now = from;
    for (; now < from + durationMs; now += frameMs) if (monitor.sample(frameMs, now)) fired += 1;
    return { fired, now };
  };

  it("no avisa a 60 FPS", () => {
    assert.equal(feed(new PerformanceMonitor(options), 0, 20000, 16.7).fired, 0);
  });

  it("avisa una sola vez tras una caída sostenida y respeta el cooldown", () => {
    const monitor = new PerformanceMonitor(options);
    const first = feed(monitor, 0, 6000, 40); // 25 FPS
    assert.equal(first.fired, 1);
    assert.equal(feed(monitor, first.now, 6000, 40).fired, 0, "dentro del cooldown");
  });

  it("ignora un tirón breve y los saltos de pestaña oculta", () => {
    const monitor = new PerformanceMonitor(options);
    const warm = feed(monitor, 0, 3000, 16.7);
    const dip = feed(monitor, warm.now, 1500, 40);
    assert.equal(dip.fired, 0);
    assert.equal(monitor.sample(5000, dip.now), false);
    assert.equal(feed(monitor, dip.now + 5000, 5000, 16.7).fired, 0);
  });

  it("reset concede un margen tras cambiar de calidad", () => {
    const monitor = new PerformanceMonitor(options);
    monitor.reset(0);
    assert.equal(feed(monitor, 0, 7000, 40).fired, 0);
  });
});
