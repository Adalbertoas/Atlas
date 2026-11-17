import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { describe, it } from "node:test";
import { fileURLToPath } from "node:url";
import { ListeningEngine, type TranscribeFn } from "./ListeningEngine.ts";
import { SileroVad, StreamingVad, VAD_CHUNK } from "./SileroVad.ts";
import { probabilityForSensitivity, SpeechSegmenter } from "./SpeechSegmenter.ts";

const FRAME = 320;
const here = (relative: string) => fileURLToPath(new URL(relative, import.meta.url));

let seed = 3;
const random = () => {
  seed = (seed * 16807) % 2147483647;
  return seed / 2147483647 - 0.5;
};

function readWav(path: string): Float32Array {
  const data = readFileSync(path).subarray(44);
  const out = new Float32Array(data.length / 2);
  for (let i = 0; i < out.length; i += 1) out[i] = data.readInt16LE(i * 2) / 32768;
  return out;
}

/** Ruido de fondo fuerte y variado: ventilador, zumbido, golpes y acordes. */
function loudNoise(seconds: number): Float32Array {
  const out = new Float32Array(Math.round(seconds * 16000));
  let brown = 0;
  for (let i = 0; i < out.length; i += 1) {
    const t = i / 16000;
    brown = 0.98 * brown + random() * 0.2;
    const hum = 0.05 * Math.sin(2 * Math.PI * 60 * t) + 0.03 * Math.sin(2 * Math.PI * 180 * t);
    const chord = 0.04 * (Math.sin(2 * Math.PI * 220 * t) + Math.sin(2 * Math.PI * 277 * t) + Math.sin(2 * Math.PI * 330 * t));
    const clank = i % 24000 < 1500 ? 0.3 * random() * Math.exp(-(i % 24000) / 300) : 0;
    out[i] = 0.25 * brown + hum + chord + clank;
  }
  return out;
}

const mix = (a: Float32Array, b: Float32Array) => Float32Array.from(a, (value, i) => value + (b[i] ?? 0));
const frames = (audio: Float32Array) => Array.from({ length: Math.floor(audio.length / FRAME) }, (_, k) => audio.subarray(k * FRAME, (k + 1) * FRAME));

describe("SpeechSegmenter con probabilidad de voz", () => {
  it("el ruido fuerte no es voz si el detector dice que no", () => {
    const segmenter = new SpeechSegmenter();
    const events = frames(loudNoise(5)).map((frame) => segmenter.push(frame, 0.05)).filter(Boolean);
    assert.deepEqual(events, []);
  });

  it("voz según el detector, con histéresis para no cortar sílabas débiles", () => {
    const segmenter = new SpeechSegmenter({ endSilenceMs: 500 });
    const audio = frames(loudNoise(3));
    const events: string[] = [];
    audio.forEach((frame, k) => {
      // 0,9 al hablar; 0,4 (entre salida y entrada) en una sílaba débil; 0,1 al callar.
      const p = k < 20 ? 0.1 : k < 50 ? 0.9 : k < 60 ? 0.4 : k < 80 ? 0.9 : 0.1;
      const event = segmenter.push(frame, p);
      if (event) events.push(event);
    });
    assert.deepEqual(events.slice(0, 3), ["start", "pause", "end"]);
  });

  it("la sensibilidad cambia la probabilidad exigida", () => {
    assert.deepEqual(probabilityForSensitivity(0.5), { enterProbability: 0.5, exitProbability: 0.35 });
    assert.ok(probabilityForSensitivity(1).enterProbability < probabilityForSensitivity(0).enterProbability);
  });
});

describe("Silero VAD (modelo real)", async () => {
  const vad = await SileroVad.create(new Uint8Array(readFileSync(here("../../../public/vad/silero_vad_v6.onnx"))));
  const speech = readWav(here("fixtures/voz-atlas.wav"));

  async function probabilities(audio: Float32Array): Promise<number[]> {
    const stream = new StreamingVad(vad);
    stream.reset();
    const out: number[] = [];
    for (const frame of frames(audio)) {
      stream.push(frame);
      await stream.flush();
      out.push(stream.probability);
    }
    return out;
  }

  it("bloques de 512 muestras", async () => {
    await assert.rejects(() => vad.process(new Float32Array(100)));
    vad.reset();
    const p = await vad.process(new Float32Array(VAD_CHUNK));
    assert.ok(p >= 0 && p < 0.2, `silencio ${p}`);
  });

  it("reconoce la voz", async () => {
    const p = await probabilities(speech);
    assert.ok(Math.max(...p) > 0.9);
    assert.ok(p.filter((value) => value >= 0.5).length > 40, "buena parte de la frase es voz");
  });

  it("el ruido fuerte (ventilador, zumbido, golpes, música) no es voz", async () => {
    const p = await probabilities(loudNoise(6));
    assert.ok(Math.max(...p) < 0.5, `máximo ${Math.max(...p)}`);
  });

  it("detecta la frase con ruido fuerte encima, de principio a fin", async () => {
    const noise = loudNoise(speech.length / 16000);
    const noisy = mix(speech, noise);
    const p = await probabilities(noisy);
    const segmenter = new SpeechSegmenter({ endSilenceMs: 550 });
    const energyOnly = new SpeechSegmenter({ endSilenceMs: 550 });
    const neural: string[] = [];
    const volume: string[] = [];
    frames(noisy).forEach((frame, k) => {
      const a = segmenter.push(frame, p[k]);
      const b = energyOnly.push(frame);
      if (a) neural.push(a);
      if (b) volume.push(b);
      if (a === "end") segmenter.finishUtterance();
      if (b === "end") energyOnly.finishUtterance();
    });
    assert.equal(neural.filter((e) => e === "start").length, 1, `neuronal: ${neural.join(",")}`);
    assert.ok(neural.includes("end"), "termina la frase aunque el ruido siga");
    // Referencia: el detector por volumen se confunde con este ruido.
    assert.notDeepEqual(volume, neural);
  });

  it("el motor ignora el ruido y escucha el comando con ruido de fondo", async () => {
    const calls: number[] = [];
    const transcribe: TranscribeFn = async (audio) => {
      calls.push(audio.length);
      return { text: "Atlas, pon algo de música relajante por favor", speakerScore: null };
    };
    const commands: string[] = [];
    const engine = new ListeningEngine(transcribe, {
      onState: () => undefined,
      onWake: () => undefined,
      onCommand: (text) => commands.push(text),
      onNothingHeard: () => undefined,
      onError: () => undefined,
      onSpeakerRejected: () => undefined,
    });
    engine.startStandby();
    const noiseOnly = loudNoise(8);
    const pNoise = await probabilities(noiseOnly);
    frames(noiseOnly).forEach((frame, k) => engine.pushFrame(frame, pNoise[k]));
    assert.equal(calls.length, 0, "8 s de ruido fuerte: ninguna transcripción");

    const noisy = mix(speech, loudNoise(speech.length / 16000));
    const pNoisy = await probabilities(noisy);
    frames(noisy).forEach((frame, k) => engine.pushFrame(frame, pNoisy[k]));
    for (let i = 0; i < 20; i += 1) await new Promise((resolve) => setImmediate(resolve));
    assert.deepEqual(commands, ["pon algo de música relajante por favor"]);
  });
});
