import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { bandLevels, EnvelopeFollower, rmsFromTimeDomain, VoiceActivityDetector } from "./audioFeatures.ts";
import { VoiceVisualizer } from "./VoiceVisualizer.ts";

const sine = (amplitude: number, length = 1024) => Uint8Array.from({ length }, (_, i) => Math.round(128 + amplitude * 127 * Math.sin((i / length) * Math.PI * 16)));

describe("rmsFromTimeDomain", () => {
  it("el silencio vale 0", () => {
    assert.equal(rmsFromTimeDomain(new Uint8Array(512).fill(128)), 0);
    assert.equal(rmsFromTimeDomain(new Uint8Array(0)), 0);
  });

  it("una senoide de amplitud A da A/√2", () => {
    assert.ok(Math.abs(rmsFromTimeDomain(sine(1)) - Math.SQRT1_2) < 0.02);
    assert.ok(Math.abs(rmsFromTimeDomain(sine(0.5)) - 0.5 * Math.SQRT1_2) < 0.02);
  });
});

describe("bandLevels", () => {
  // 512 bins a 48 kHz: 46,875 Hz por bin.
  const spectrum = (fromHz: number, toHz: number) => {
    const bins = new Uint8Array(512);
    for (let i = 0; i < bins.length; i += 1) {
      const hz = i * (48000 / 1024);
      if (hz >= fromHz && hz < toHz) bins[i] = 255;
    }
    return bins;
  };

  it("separa graves, medios y agudos", () => {
    const bass = bandLevels(spectrum(40, 240), 48000);
    assert.ok(bass.bass > 0.6 && bass.mid < 0.1 && bass.treble === 0);
    const mid = bandLevels(spectrum(300, 1900), 48000);
    assert.ok(mid.mid > 0.8 && mid.bass < 0.3 && mid.treble < 0.05);
    const treble = bandLevels(spectrum(2100, 7900), 48000);
    assert.ok(treble.treble > 0.9 && treble.bass === 0 && treble.mid < 0.05);
  });

  it("normaliza a 0..1 y el silencio da 0", () => {
    assert.deepEqual(bandLevels(new Uint8Array(512), 48000), { bass: 0, mid: 0, treble: 0 });
    const full = bandLevels(new Uint8Array(512).fill(255), 48000);
    assert.ok(Math.abs(full.bass - 1) < 1e-9 && Math.abs(full.mid - 1) < 1e-9 && Math.abs(full.treble - 1) < 1e-9);
  });
});

describe("EnvelopeFollower", () => {
  it("sube rápido y baja despacio", () => {
    const envelope = new EnvelopeFollower(30, 5);
    const risen = envelope.update(1, 0.05);
    assert.ok(risen > 0.7, `ataque ${risen}`);
    const fallen = envelope.update(0, 0.05);
    assert.ok(fallen > risen * 0.7, `relajación ${fallen}`);
  });

  it("nunca sobrepasa la entrada ni salta", () => {
    const envelope = new EnvelopeFollower();
    let previous = 0;
    for (let i = 0; i < 120; i += 1) {
      const value = envelope.update(i % 20 < 10 ? 1 : 0, 1 / 60);
      assert.ok(value >= 0 && value <= 1);
      assert.ok(Math.abs(value - previous) < 0.45);
      previous = value;
    }
  });
});

describe("VoiceActivityDetector", () => {
  const options = { enter: 0.04, exit: 0.02, hangoverMs: 300 };

  it("usa histéresis entre los umbrales de entrada y salida", () => {
    const vad = new VoiceActivityDetector(options);
    assert.equal(vad.update(0.03, 0), false);
    assert.equal(vad.update(0.05, 10), true);
    assert.equal(vad.update(0.03, 20), true, "por encima del umbral de salida sigue activa");
  });

  it("aguanta las pausas cortas y se apaga tras el silencio", () => {
    const vad = new VoiceActivityDetector(options);
    vad.update(0.1, 0);
    assert.equal(vad.update(0, 200), true, "pausa entre sílabas");
    assert.equal(vad.update(0, 350), false);
  });
});

describe("VoiceVisualizer", () => {
  it("sin señal analizable los niveles decaen a cero: no inventa movimiento", () => {
    const visualizer = new VoiceVisualizer();
    for (let i = 0; i < 30; i += 1) visualizer.update({ rms: 0.2, bass: 0.5, mid: 0.5, treble: 0.5 }, 1 / 60, i * 16);
    let levels = visualizer.update(null, 1 / 60, 500);
    assert.ok(levels.level > 0.3, "decae, no se corta");
    for (let i = 0; i < 240; i += 1) levels = visualizer.update(null, 1 / 60, 520 + i * 16);
    assert.ok(levels.level < 0.001 && levels.bass < 0.001 && levels.mid < 0.001 && levels.treble < 0.001);
    assert.equal(levels.voiceActive, false);
  });

  it("escala la voz normal a un nivel útil y acota a 1", () => {
    const visualizer = new VoiceVisualizer();
    let levels = visualizer.update({ rms: 0.12, bass: 0.3, mid: 0.4, treble: 0.1 }, 1 / 60, 0);
    for (let i = 1; i < 60; i += 1) levels = visualizer.update({ rms: 0.12, bass: 0.3, mid: 0.4, treble: 0.1 }, 1 / 60, i * 16);
    assert.ok(levels.level > 0.4 && levels.level < 0.7, `nivel ${levels.level}`);
    assert.equal(levels.voiceActive, true);
    for (let i = 0; i < 60; i += 1) levels = visualizer.update({ rms: 1, bass: 1, mid: 1, treble: 1 }, 1 / 60, 1000 + i * 16);
    assert.ok(levels.level <= 1 && levels.bass <= 1);
  });
});
