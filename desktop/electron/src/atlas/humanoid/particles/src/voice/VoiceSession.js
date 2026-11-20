// ATLAS Fase 5F — ciclo de interacción por voz, desacoplado del proveedor de IA.
//   activar escucha → LISTENING (micrófono abierto, el núcleo reacciona al nivel real)
//   inicio de voz → (sigue LISTENING) · final de voz → THINKING mientras el procesador trabaja
//   el procesador avisa de una herramienta → EXECUTING (y vuelve a THINKING al terminar)
//   hay audio de respuesta → SPEAKING cuando EMPIEZA a sonar, pulsos con su amplitud real → IDLE al terminar
//   cualquier fallo → ERROR y, tras errorRecoverMs, IDLE.
// Cada cambio de estado responde a un evento real (micrófono, procesador, reproducción): no hay temporizadores que
// finjan que ATLAS escucha, piensa o habla.
//
// Contrato del procesador (cualquier proveedor):
//   process({ audio?: Blob, text?: string }, { toolStart(name), toolEnd(name), signal: AbortSignal })
//     → Promise<{ text?: string, audio?: Blob | ArrayBuffer | string(URL) }>
import { MicrophoneInput, SpeechOutput } from "./AudioIO.js";

export class VoiceSession extends EventTarget {
  /**
   * @param {{voice: import('./VoiceStateController.js').VoiceStateController, processor: object,
   *          mic?: MicrophoneInput, output?: SpeechOutput, errorRecoverMs?: number, continuous?: boolean}} o
   */
  constructor({ voice, processor, mic = new MicrophoneInput(), output = new SpeechOutput(), errorRecoverMs = 1800, continuous = false }) {
    super();
    Object.assign(this, { voice, processor, mic, output, errorRecoverMs, continuous });
    this.phase = "idle"; this.log = []; this.abort = null;
    this._onEnd = () => this._speechEnded();
    this._onStart = () => this._event("inicio de voz");
    mic.addEventListener("speechend", this._onEnd);
    mic.addEventListener("speechstart", this._onStart);
    output.addEventListener("start", () => { this._event("audio de respuesta sonando"); this.voice.setState("speaking", { source: "reproducción" }); });
  }

  _event(what, extra = {}) { const e = { t: +(performance.now() / 1000).toFixed(3), evento: what, estado: this.voice.state, ...extra }; this.log.push(e); if (this.log.length > 200) this.log.shift(); this.dispatchEvent(new CustomEvent("event", { detail: e })); }

  /** "Activar escucha". Devuelve false si no hay micrófono (estado ERROR y luego IDLE). */
  async activate() {
    if (this.phase !== "idle") return false;
    this.output.unlock();                      // en el mismo gesto del usuario: permite reproducir la respuesta
    this.phase = "listening";
    const ok = await this.mic.start();
    if (!ok) { this.phase = "idle"; this._fail(`micrófono: ${this.mic.lastMessage || this.mic.status}`); return false; }
    this._event("micrófono abierto");
    this.voice.setState("listening", { source: "micrófono" });
    return true;
  }

  /** Llamar cada frame: lleva el audio real (micrófono o respuesta) al avatar. */
  tick() {
    if (this.phase === "listening" && this.mic.status === "running") this.voice.setAudioSamples(this.mic.getSamples());
    else if (this.output.playing) this.voice.setAudioSamples(this.output.getSamples());
  }

  async _speechEnded() {
    if (this.phase !== "listening") return;
    this.phase = "processing";
    const audio = await this.mic.stop();
    this._event("final de voz", { bytes: audio?.size ?? 0 });
    this.voice.setState("thinking", { source: "final de voz" });
    this.abort = new AbortController();
    let result;
    try {
      result = await this.processor.process({ audio }, {
        signal: this.abort.signal,
        toolStart: name => { this._event("herramienta", { nombre: name }); this.voice.setState("executing", { source: `herramienta ${name}` }); },
        toolEnd: name => { this._event("herramienta terminada", { nombre: name }); this.voice.setState("thinking", { source: `fin de ${name}` }); },
      });
    } catch (err) {
      if (this.abort?.signal.aborted) return;
      this.phase = "idle"; this._fail(`procesador: ${err.message}`); return;
    }
    if (this.abort?.signal.aborted) return;
    this._event("respuesta lista", { texto: result?.text ?? null, conAudio: !!result?.audio });
    if (result?.audio) {
      this.phase = "speaking";
      const reason = await this.output.play(result.audio);
      this._event("audio de respuesta terminado", { motivo: reason });
      if (reason === "error") { this.phase = "idle"; this._fail(`reproducción: ${this.output.lastError || "error"}`); return; }
    }
    this.phase = "idle";
    this.voice.setState("idle", { source: result?.audio ? "fin de la respuesta" : "respuesta sin audio" });
    if (this.continuous) this.activate();
  }

  _fail(message) {
    this._event("error", { mensaje: message });
    this.voice.setState("error", { source: message });
    clearTimeout(this._rec);
    this._rec = setTimeout(() => { if (this.voice.state === "error") this.voice.setState("idle", { source: "recuperación tras error" }); }, this.errorRecoverMs);
  }

  /** Cancela todo y vuelve a IDLE. */
  async cancel() {
    this.abort?.abort(); this.output.stop();
    if (this.mic.status === "running") await this.mic.stop();
    this.phase = "idle"; this._event("cancelado");
    this.voice.setState("idle", { source: "cancelado" });
  }

  dispose() {
    clearTimeout(this._rec); this.abort?.abort();
    this.mic.removeEventListener("speechend", this._onEnd); this.mic.removeEventListener("speechstart", this._onStart);
    this.mic.stop(); this.output.dispose();
  }
}

/** Procesador de PRUEBA del laboratorio: devuelve tu propia grabación como "respuesta". No es IA ni lo finge:
 *  sirve para comprobar el ciclo completo con audio real (micrófono → pensar → hablar → idle). */
export class EchoProcessor {
  constructor({ decodeAsTool = false } = {}) { this.decodeAsTool = decodeAsTool; this.name = "eco (prueba)"; }
  async process({ audio }, hooks) {
    if (!audio || !audio.size) throw new Error("no se grabó audio");
    const buf = await audio.arrayBuffer();                       // trabajo real: leer la grabación
    // decodificación real, expuesta como "herramienta" para probar EXECUTING
    if (this.decodeAsTool) { hooks.toolStart("decodificar"); const c = new AudioContext(); await c.decodeAudioData(buf.slice(0)).catch(() => null); await c.close().catch(() => {}); hooks.toolEnd("decodificar"); }
    return { text: null, audio: new Blob([buf], { type: audio.type }) };
  }
}
