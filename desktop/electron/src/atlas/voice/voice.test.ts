import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { ListeningEngine, type TranscribeFn } from "./ListeningEngine.ts";
import { encodeWav, FrameAssembler, frameDb, StreamingResampler } from "./pcm.ts";
import { marginForSensitivity, SpeechSegmenter } from "./SpeechSegmenter.ts";
import { cleanTranscript, detectWakeWord, levenshtein } from "./wakeWord.ts";

const FRAME = 320; // 20 ms a 16 kHz

let seed = 7;
const random = () => {
  seed = (seed * 16807) % 2147483647;
  return seed / 2147483647 - 0.5;
};
const noiseFrame = (amplitude = 0.004) => Float32Array.from({ length: FRAME }, () => random() * 2 * amplitude);
let phase = 0;
const voiceFrame = (amplitude = 0.3) =>
  Float32Array.from({ length: FRAME }, () => {
    phase += (2 * Math.PI * 220) / 16000;
    return amplitude * Math.sin(phase) + random() * 0.004;
  });
const frames = (count: number, make: () => Float32Array) => Array.from({ length: count }, make);
const ms = (value: number) => Math.round(value / 20);

describe("pcm", () => {
  it("frameDb: escala completa ≈ -3 dB, silencio -100", () => {
    assert.equal(frameDb(new Float32Array(FRAME)), -100);
    const full = Float32Array.from({ length: 1600 }, (_, i) => Math.sin((i / 1600) * Math.PI * 20));
    assert.ok(Math.abs(frameDb(full) + 3.01) < 0.1);
  });

  it("encodeWav produce un WAV PCM16 mono válido", () => {
    const wav = encodeWav(Float32Array.from([0, 0.5, -1, 1]), 16000);
    const view = new DataView(wav.buffer);
    assert.equal(String.fromCharCode(...wav.slice(0, 4)), "RIFF");
    assert.equal(String.fromCharCode(...wav.slice(8, 12)), "WAVE");
    assert.equal(view.getUint16(22, true), 1);
    assert.equal(view.getUint32(24, true), 16000);
    assert.equal(view.getUint16(34, true), 16);
    assert.equal(view.getUint32(40, true), 8);
    assert.deepEqual([0, 1, 2, 3].map((i) => view.getInt16(44 + i * 2, true)), [0, 16383, -32768, 32767]);
  });

  it("el remuestreo 48k→16k conserva duración y forma, sin saltos entre bloques", () => {
    const resampler = new StreamingResampler(48000, 16000);
    const tone = (i: number) => Math.sin((2 * Math.PI * 440 * i) / 48000);
    const out: number[] = [];
    // Bloques de 128 (lo que entrega el AudioWorklet).
    for (let start = 0; start < 48000; start += 128) {
      out.push(...resampler.process(Float32Array.from({ length: 128 }, (_, k) => tone(start + k))));
    }
    assert.ok(Math.abs(out.length - 16000) <= 2, `longitud ${out.length}`);
    let maxError = 0;
    for (let i = 0; i < out.length; i += 1) maxError = Math.max(maxError, Math.abs(out[i] - Math.sin((2 * Math.PI * 440 * i) / 16000)));
    assert.ok(maxError < 0.02, `error ${maxError}`);
  });

  it("a la misma frecuencia no toca el audio", () => {
    const input = Float32Array.from([0.1, 0.2]);
    assert.equal(new StreamingResampler(16000, 16000).process(input), input);
  });

  it("FrameAssembler agrupa bloques de 128 en tramas de 320", () => {
    const assembler = new FrameAssembler(FRAME);
    const got: number[] = [];
    for (let i = 0; i < 10; i += 1) assembler.push(Float32Array.from({ length: 128 }, (_, k) => i * 128 + k), (frame) => got.push(frame[0], frame.length));
    assert.deepEqual(got, [0, 320, 320, 320, 640, 320, 960, 320]);
  });
});

describe("SpeechSegmenter", () => {
  const feed = (segmenter: SpeechSegmenter, list: Float32Array[]) => list.map((frame) => segmenter.push(frame)).filter(Boolean);

  it("detecta inicio, pausa y fin de una frase sobre ruido de fondo", () => {
    const segmenter = new SpeechSegmenter({ endSilenceMs: 700, pauseMs: 300 });
    assert.deepEqual(feed(segmenter, frames(ms(1000), () => noiseFrame())), []);
    assert.deepEqual(feed(segmenter, frames(ms(800), () => voiceFrame())), ["start"]);
    assert.ok(segmenter.active);
    assert.deepEqual(feed(segmenter, frames(ms(700), () => noiseFrame())), ["pause", "end"]);
  });

  it("conserva el pre-roll y sabe dónde termina la voz", () => {
    const segmenter = new SpeechSegmenter({ preRollMs: 300 });
    feed(segmenter, frames(ms(1000), () => noiseFrame()));
    feed(segmenter, frames(ms(500), () => voiceFrame()));
    feed(segmenter, frames(ms(200), () => noiseFrame()));
    // 300 ms de pre-roll (sus últimos 120 ms son la voz que confirmó el inicio)
    // + los 380 ms de voz restantes + 200 ms de silencio.
    assert.equal(segmenter.durationMs, 300 + 380 + 200);
    assert.ok(segmenter.voicedMs >= 480 && segmenter.voicedMs <= 520, `voz ${segmenter.voicedMs}`);
    assert.equal(segmenter.voicedEndSamples, (segmenter.durationMs - 200) * 16);
    assert.equal(segmenter.audio().length, segmenter.sampleCount);
  });

  it("no corta en pausas cortas entre palabras", () => {
    const segmenter = new SpeechSegmenter({ endSilenceMs: 700 });
    feed(segmenter, frames(ms(500), () => noiseFrame()));
    const events = feed(segmenter, [...frames(ms(400), () => voiceFrame()), ...frames(ms(400), () => noiseFrame()), ...frames(ms(400), () => voiceFrame())]);
    assert.deepEqual(events, ["start", "pause"]);
    assert.ok(segmenter.active);
  });

  it("ignora clics más cortos que minSpeechMs", () => {
    const segmenter = new SpeechSegmenter({ minSpeechMs: 120 });
    feed(segmenter, frames(ms(500), () => noiseFrame()));
    assert.deepEqual(feed(segmenter, [...frames(ms(60), () => voiceFrame()), ...frames(ms(300), () => noiseFrame())]), []);
  });

  it("se adapta a un ruido de fondo alto y constante (ventilador)", () => {
    const segmenter = new SpeechSegmenter({ maxUtteranceMs: 4000 });
    // El ruido fuerte supera el umbral absoluto: al principio puede parecer voz…
    feed(segmenter, frames(ms(5000), () => noiseFrame(0.05)));
    segmenter.finishUtterance();
    // …pero el fondo se recalibra y deja de dispararse.
    assert.deepEqual(feed(segmenter, frames(ms(3000), () => noiseFrame(0.05))), []);
    // Y la voz por encima de ese fondo se sigue detectando.
    assert.deepEqual(feed(segmenter, frames(ms(400), () => voiceFrame(0.5))), ["start"]);
  });

  it("corta frases que superan la duración máxima", () => {
    const segmenter = new SpeechSegmenter({ maxUtteranceMs: 1000 });
    feed(segmenter, frames(ms(500), () => noiseFrame()));
    const events = feed(segmenter, frames(ms(1200), () => voiceFrame()));
    // "end" se repite hasta que quien consume la frase llama a finishUtterance().
    assert.deepEqual(events.slice(0, 2), ["start", "end"]);
    segmenter.finishUtterance();
    assert.equal(segmenter.active, false);
  });

  it("la sensibilidad baja el margen sobre el ruido", () => {
    assert.equal(marginForSensitivity(0), 18);
    assert.equal(marginForSensitivity(1), 6);
    assert.ok(marginForSensitivity(0.5) < marginForSensitivity(0.2));
  });
});

describe("palabra de activación", () => {
  it("detecta Atlas al principio y separa el comando", () => {
    assert.deepEqual(detectWakeWord("Atlas, ¿qué hora es?"), { detected: true, command: "¿qué hora es?" });
    assert.deepEqual(detectWakeWord("Atlas."), { detected: true, command: "" });
    assert.deepEqual(detectWakeWord("Oye Atlas, apaga la luz"), { detected: true, command: "apaga la luz" });
    assert.deepEqual(detectWakeWord("hola, atlas: pon música"), { detected: true, command: "pon música" });
    assert.equal(detectWakeWord("ÁTLAS abre el navegador").command, "abre el navegador");
  });

  it("tolera cómo Whisper oye mal el nombre", () => {
    for (const heard of ["Hatlas, hola", "Adlas, hola", "At las, hola", "Atla, hola", "Attlas hola", "Atlaz hola"]) {
      assert.ok(detectWakeWord(heard).detected, heard);
    }
  });

  it("no se activa con Atlas a mitad de frase ni con palabras parecidas", () => {
    for (const heard of ["el atlas de geografía está en la mesa", "las aulas están vacías", "altas montañas", "alas de mariposa", "atrás", "", "  "]) {
      assert.equal(detectWakeWord(heard).detected, false, heard);
    }
  });

  it("levenshtein", () => {
    assert.equal(levenshtein("atlas", "atlas"), 0);
    assert.equal(levenshtein("atlas", "adlas"), 1);
    assert.equal(levenshtein("atlas", "altas"), 2);
  });

  it("descarta alucinaciones típicas de Whisper", () => {
    for (const junk of ["¡Gracias por ver el video!", "Subtítulos realizados por la comunidad de Amara.org", "¡Adiós!", "...", "Música", ""]) {
      assert.equal(cleanTranscript(junk), "", junk);
    }
    assert.equal(cleanTranscript("  Atlas,   gracias por todo "), "Atlas, gracias por todo");
  });
});

// ---------- Motor ----------

type Call = { seconds: number; fast: boolean; speaker: boolean; done: boolean; resolve: (text: string, speakerScore?: number | null) => void; reject: (error: Error) => void };

const flush = async () => {
  for (let i = 0; i < 4; i += 1) await new Promise((resolve) => setImmediate(resolve));
};

function harness(options: { handsFree?: boolean; speakerThreshold?: number } = {}) {
  const calls: Call[] = [];
  const transcribe: TranscribeFn = (audio, { fast, speaker }) =>
    new Promise((resolve, reject) => {
      const call: Call = {
        seconds: audio.length / 16000,
        fast,
        speaker,
        done: false,
        resolve: (text, speakerScore = null) => {
          call.done = true;
          resolve({ text, speakerScore });
        },
        reject: (error) => {
          call.done = true;
          reject(error);
        },
      };
      calls.push(call);
    });
  const log: string[] = [];
  const commands: string[] = [];
  const engine = new ListeningEngine(transcribe, {
    onState: () => undefined,
    onWake: () => log.push("wake"),
    onCommand: (text) => commands.push(text),
    onNothingHeard: (reason) => log.push(`nothing:${reason}`),
    onError: (message) => log.push(`error:${message}`),
    onSpeakerRejected: (score) => log.push(`rejected:${score}`),
  });
  if (options.speakerThreshold !== undefined) engine.setSpeakerGate(options.speakerThreshold);
  if (options.handsFree) engine.startStandby();
  const push = (count: number, make: () => Float32Array) => {
    for (let i = 0; i < count; i += 1) engine.pushFrame(make());
  };
  const open = () => calls.filter((call) => !call.done);
  /** Resuelve todas las transcripciones pendientes, también las que se encadenan. */
  const settle = async (text: string | ((call: Call) => string), speakerScore: number | null = null) => {
    for (let round = 0; round < 10; round += 1) {
      await flush();
      const pending = open();
      if (!pending.length) return;
      for (const call of pending) call.resolve(typeof text === "function" ? text(call) : text, call.speaker ? speakerScore : null);
    }
    throw new Error("las transcripciones no terminan nunca");
  };
  // En reposo: calibra el ruido de fondo como haría la sala real.
  if (options.handsFree) push(ms(1000), () => noiseFrame());
  return { engine, calls, log, commands, push, open, settle };
}

describe("ListeningEngine", () => {
  it("'Atlas, …' de un tirón: se activa con la parcial y envía el comando al callar", async () => {
    const h = harness({ handsFree: true });
    h.push(ms(1200), () => voiceFrame());
    assert.equal(h.calls.length, 1, "una parcial temprana");
    assert.equal(h.calls[0].fast, true);
    h.calls[0].resolve("Atlas, qué hora");
    await flush();
    assert.deepEqual(h.log, ["wake"], "se activa mientras todavía habla");
    assert.equal(h.engine.current.capturing, true);
    assert.equal(h.engine.current.partial, "qué hora");

    h.push(ms(600), () => voiceFrame());
    h.push(ms(400), () => noiseFrame());
    await h.settle("Atlas, qué hora es");
    const anticipated = h.calls.at(-1)!;
    assert.equal(anticipated.fast, false, "la pausa lanzó la transcripción anticipada");
    const before = h.calls.length;
    h.push(ms(500), () => noiseFrame());
    await h.settle("no debería pedirse");
    assert.equal(h.calls.length, before, "la anticipada cubría toda la voz: no hay transcripción extra");
    assert.deepEqual(h.commands, ["qué hora es"]);
    assert.equal(h.engine.current.mode, "standby");
  });

  it("'Atlas' suelto: espera el comando en la siguiente frase", async () => {
    const h = harness({ handsFree: true });
    h.push(ms(500), () => voiceFrame());
    h.push(ms(600), () => noiseFrame());
    await h.settle("Atlas.");
    assert.deepEqual(h.log, ["wake"]);
    assert.equal(h.engine.current.mode, "command");
    assert.equal(h.engine.current.capturing, true);

    h.push(ms(900), () => voiceFrame());
    h.push(ms(900), () => noiseFrame());
    await h.settle("Apaga la luz del salón.");
    assert.deepEqual(h.commands, ["Apaga la luz del salón."]);
  });

  it("'Atlas', pausa corta y el comando antes de que llegue la transcripción de 'Atlas'", async () => {
    const h = harness({ handsFree: true });
    h.push(ms(500), () => voiceFrame());
    h.push(ms(600), () => noiseFrame()); // termina "Atlas." y se transcribe…
    const wake = h.open();
    assert.ok(wake.length >= 1);
    // …pero ya empezó el comando, y su primera parcial llega antes.
    h.push(ms(1300), () => voiceFrame());
    await flush();
    for (const call of h.open().filter((call) => !wake.includes(call))) call.resolve("Cuál es la capital de Francia");
    await flush();
    for (const call of wake) call.resolve("Atlas.");
    await flush();
    assert.deepEqual(h.log, ["wake"]);
    assert.equal(h.engine.current.capturing, true, "la frase en curso pasa a ser el comando");
    h.push(ms(700), () => voiceFrame());
    h.push(ms(900), () => noiseFrame());
    await h.settle("¿Cuál es la capital de Francia?");
    assert.deepEqual(h.commands, ["¿Cuál es la capital de Francia?"]);
  });

  it("conversación de fondo sin 'Atlas': se abandona tras la primera parcial", async () => {
    const h = harness({ handsFree: true });
    h.push(ms(1200), () => voiceFrame());
    h.calls[0].resolve("y entonces le dije que no");
    await flush();
    h.push(ms(3000), () => voiceFrame());
    h.push(ms(800), () => noiseFrame());
    await h.settle("no debería pedirse");
    assert.equal(h.calls.length, 1, "no se vuelve a transcribir la frase ignorada");
    assert.deepEqual(h.commands, []);
    assert.deepEqual(h.log, []);
    assert.equal(h.engine.current.capturing, false);
  });

  it("'Atlas' a mitad de una frase de fondo no activa nada", async () => {
    const h = harness({ handsFree: true });
    h.push(ms(700), () => voiceFrame());
    h.push(ms(700), () => noiseFrame());
    await h.settle("busca el atlas de geografía");
    assert.deepEqual(h.log, []);
    assert.deepEqual(h.commands, []);
  });

  it("botón del micrófono: escucha sin palabra, muestra el texto y corta solo al callar", async () => {
    const h = harness();
    h.engine.startCommand("manual");
    assert.equal(h.engine.current.mode, "command");
    // Empieza a hablar en cuanto se abre el micrófono (sin calibrar el fondo).
    h.push(ms(1500), () => voiceFrame());
    assert.ok(h.calls.length >= 1, "parcial mientras habla");
    h.calls[0].resolve("Pon música");
    await flush();
    assert.equal(h.engine.current.partial, "Pon música");
    h.push(ms(900), () => noiseFrame());
    await h.settle("Pon música relajante");
    assert.deepEqual(h.commands, ["Pon música relajante"]);
    assert.equal(h.engine.current.mode, "off", "sin manos libres vuelve a apagarse");
  });

  it("si la frase siguió después de la anticipada, transcribe la frase entera", async () => {
    const h = harness();
    h.engine.startCommand("manual");
    h.push(ms(400), () => voiceFrame());
    h.push(ms(400), () => noiseFrame()); // pausa → anticipada
    h.push(ms(400), () => voiceFrame()); // sigue hablando
    h.push(ms(900), () => noiseFrame());
    await h.settle((call) => (call.seconds < 1 ? "abre" : "abre el navegador"));
    assert.deepEqual(h.commands, ["abre el navegador"]);
  });

  it("botón sin hablar: avisa que no oyó nada", () => {
    const h = harness();
    h.engine.startCommand("manual");
    h.push(ms(8100), () => noiseFrame());
    assert.deepEqual(h.log, ["nothing:manual"]);
    assert.equal(h.engine.current.mode, "off");
  });

  it("botón y transcripción vacía: avisa que no entendió", async () => {
    const h = harness();
    h.engine.startCommand("manual");
    h.push(ms(600), () => voiceFrame());
    h.push(ms(900), () => noiseFrame());
    await h.settle("¡Gracias por ver el video!");
    assert.deepEqual(h.log, ["nothing:manual"]);
    assert.deepEqual(h.commands, []);
  });

  it("tras 'Atlas' el silencio no es un error: vuelve al reposo", () => {
    const h = harness({ handsFree: true });
    h.engine.startCommand("wake");
    h.push(ms(6100), () => noiseFrame());
    assert.deepEqual(h.log, []);
    assert.equal(h.engine.current.mode, "standby");
  });

  it("un golpe mientras espera el comando no cancela la espera", async () => {
    const h = harness();
    h.engine.startCommand("manual");
    h.push(ms(500), () => noiseFrame());
    h.push(ms(140), () => voiceFrame());
    h.push(ms(900), () => noiseFrame());
    await flush();
    assert.equal(h.calls.length, 0, "no se transcribe un golpe");
    assert.equal(h.engine.current.mode, "command");
    assert.deepEqual(h.log, []);
  });

  it("en pausa (ATLAS hablando) no escucha, y al reanudar ignora el eco", () => {
    const h = harness({ handsFree: true });
    h.engine.pause();
    h.push(ms(2000), () => voiceFrame());
    assert.equal(h.calls.length, 0);
    h.engine.resume(300);
    h.push(ms(300), () => voiceFrame());
    assert.equal(h.engine.current.capturing, false);
    assert.equal(h.calls.length, 0);
    assert.equal(h.engine.current.mode, "standby");
  });

  it("no entrega al VAD el audio de una pausa ni la cola antieco", () => {
    const h = harness({ handsFree: true });
    assert.equal(h.engine.acceptsVadAudio, true);
    h.engine.pause();
    assert.equal(h.engine.acceptsVadAudio, false);
    h.engine.resume(300);
    assert.equal(h.engine.acceptsVadAudio, false);
    h.push(ms(300), () => voiceFrame());
    assert.equal(h.engine.acceptsVadAudio, true);
  });

  it("una transcripción que llega tras pausar se descarta", async () => {
    const h = harness();
    h.engine.startCommand("manual");
    h.push(ms(800), () => voiceFrame());
    h.push(ms(900), () => noiseFrame());
    await flush();
    h.engine.pause();
    await h.settle("borra todo");
    assert.deepEqual(h.commands, []);
  });

  it("seguimiento tras responder: acepta la siguiente frase sin 'Atlas'", async () => {
    const h = harness({ handsFree: true });
    h.engine.startCommand("follow-up");
    h.push(ms(700), () => voiceFrame());
    h.push(ms(900), () => noiseFrame());
    await h.settle("¿y mañana?");
    assert.deepEqual(h.commands, ["¿y mañana?"]);
  });

  it("sin manos libres, el seguimiento no abre el micrófono", () => {
    const h = harness();
    h.engine.startCommand("follow-up");
    assert.equal(h.engine.current.mode, "off");
  });

  it("detener y enviar con el botón no espera al silencio", async () => {
    const h = harness();
    h.engine.startCommand("manual");
    h.push(ms(500), () => voiceFrame());
    h.engine.finishNow();
    await h.settle("hola");
    assert.deepEqual(h.commands, ["hola"]);
  });

  it("un fallo del backend se informa y no deja el motor colgado", async () => {
    const h = harness({ handsFree: true });
    h.push(ms(500), () => voiceFrame());
    h.push(ms(600), () => noiseFrame());
    // El backend falla en todas las peticiones (también en el reintento con la frase completa).
    for (let round = 0; round < 5; round += 1) {
      await flush();
      for (const call of h.open()) call.reject(new Error("HTTP 500"));
    }
    assert.ok(h.log.some((entry) => entry.includes("HTTP 500")));
    assert.equal(h.open().length, 0);
    assert.equal(h.engine.current.mode, "standby");
    assert.equal(h.engine.current.finalizing, false);
  });

  it("apagar la escucha continua deja el motor apagado", () => {
    const h = harness({ handsFree: true });
    h.engine.stopStandby();
    assert.equal(h.engine.current.mode, "off");
    h.push(ms(1500), () => voiceFrame());
    assert.equal(h.calls.length, 0);
  });

  // ---------- Solo mi voz ----------

  it("solo mi voz: 'Atlas, …' con la voz registrada se obedece", async () => {
    const h = harness({ handsFree: true, speakerThreshold: 0.5 });
    h.push(ms(1200), () => voiceFrame());
    assert.equal(h.calls[0].speaker, true, "pide la puntuación de voz");
    h.calls[0].resolve("Atlas, qué hora", 0.82);
    await flush();
    assert.deepEqual(h.log, ["wake"]);
    h.push(ms(400), () => voiceFrame());
    h.push(ms(900), () => noiseFrame());
    await h.settle("Atlas, qué hora es", 0.8);
    assert.deepEqual(h.commands, ["qué hora es"]);
  });

  it("solo mi voz: otra voz que dice 'Atlas, …' se ignora y se avisa", async () => {
    const h = harness({ handsFree: true, speakerThreshold: 0.5 });
    h.push(ms(1200), () => voiceFrame());
    h.calls[0].resolve("Atlas, apaga todo", 0.21);
    await flush();
    assert.deepEqual(h.log, [], "no se activa con la parcial");
    assert.equal(h.engine.current.capturing, false);
    h.push(ms(400), () => voiceFrame());
    h.push(ms(900), () => noiseFrame());
    await h.settle("Atlas, apaga todo", 0.24);
    assert.deepEqual(h.commands, []);
    assert.deepEqual(h.log, ["rejected:0.24"]);
    assert.equal(h.engine.current.mode, "standby");
  });

  it("solo mi voz: tras mi 'Atlas', el comando de otra persona no se envía", async () => {
    const h = harness({ handsFree: true, speakerThreshold: 0.5 });
    h.push(ms(500), () => voiceFrame());
    h.push(ms(600), () => noiseFrame());
    await h.settle("Atlas.", 0.78);
    assert.equal(h.engine.current.mode, "command");
    h.push(ms(900), () => voiceFrame());
    h.push(ms(900), () => noiseFrame());
    await h.settle("Compra mil euros en bitcoins", 0.3);
    assert.deepEqual(h.commands, []);
    assert.ok(h.log.includes("rejected:0.3"));
  });

  it("solo mi voz: el seguimiento tras responder también se verifica", async () => {
    const h = harness({ handsFree: true, speakerThreshold: 0.5 });
    h.engine.startCommand("follow-up");
    h.push(ms(700), () => voiceFrame());
    h.push(ms(900), () => noiseFrame());
    await h.settle("¿y mañana?", 0.12);
    assert.deepEqual(h.commands, []);
  });

  it("solo mi voz: el botón del micrófono no se filtra", async () => {
    const h = harness({ speakerThreshold: 0.5 });
    h.engine.startCommand("manual");
    h.push(ms(700), () => voiceFrame());
    h.push(ms(900), () => noiseFrame());
    await h.settle("Pon música", 0.1);
    assert.ok(h.calls.every((call) => !call.speaker), "no pide la puntuación");
    assert.deepEqual(h.commands, ["Pon música"]);
  });

  it("solo mi voz: si no se pudo verificar la voz de un comando, no se envía", async () => {
    const h = harness({ handsFree: true, speakerThreshold: 0.5 });
    h.push(ms(800), () => voiceFrame());
    h.push(ms(700), () => noiseFrame());
    await h.settle("Atlas, abre el correo", null);
    assert.deepEqual(h.commands, []);
    assert.deepEqual(h.log, ["rejected:null"]);
  });

  it("solo mi voz: otra voz que el backend ni transcribe se ignora en silencio", async () => {
    const h = harness({ handsFree: true, speakerThreshold: 0.5 });
    h.push(ms(2500), () => voiceFrame());
    h.push(ms(700), () => noiseFrame());
    await h.settle("", 0.2);
    assert.deepEqual(h.commands, []);
    assert.deepEqual(h.log, [], "sin avisos: no se sabe si dijo 'Atlas'");
    assert.equal(h.engine.current.mode, "standby");
  });
});

