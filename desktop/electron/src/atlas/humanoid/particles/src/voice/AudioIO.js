// ATLAS Fase 5F — entrada (micrófono) y salida (voz de ATLAS) de audio con análisis real.
// Misma técnica que el dashboard (AnalyserNode + getByteTimeDomainData, un solo elemento <audio> reutilizado y
// desbloqueado en el primer gesto del usuario), para el laboratorio o para anfitriones que no tengan ya ese sistema.
// El dashboard de ATLAS YA tiene micrófono, VAD por silencio, STT y TTS: allí NO hace falta esto; basta con llamar a
// avatar.setState / avatar.setAudioSamples como ya hace con Atlas3D (ver docs/5F_informe.md).

/** Detector de voz por nivel (sin red neuronal), con los umbrales del dashboard: pico ≥ 0,045 es voz y 1,6 s de
 *  silencio cierran la intervención. minSpeechMs evita que un golpe aislado cuente como inicio de voz. */
export class VoiceActivityDetector {
  constructor({ speechLevel = 0.045, silenceMs = 1600, minSpeechMs = 120 } = {}) {
    Object.assign(this, { speechLevel, silenceMs, minSpeechMs });
    this.reset();
  }
  reset() { this.speaking = false; this.aboveSince = null; this.lastAbove = -Infinity; this.startedAt = null; }
  /** peak: 0–1; tMs: marca de tiempo. Devuelve "start", "end" o null. */
  process(peak, tMs) {
    const above = peak >= this.speechLevel;
    if (above) { this.lastAbove = tMs; if (this.aboveSince === null) this.aboveSince = tMs; } else this.aboveSince = null;
    if (!this.speaking && above && tMs - this.aboveSince >= this.minSpeechMs) { this.speaking = true; this.startedAt = this.aboveSince; return "start"; }
    if (this.speaking && tMs - this.lastAbove >= this.silenceMs) { this.speaking = false; return "end"; }
    return null;
  }
}

const peakOf = buf => { let p = 0; for (let i = 0; i < buf.length; i++) { const v = Math.abs(buf[i] - 128) / 128; if (v > p) p = v; } return p; };
/** Reduce un búfer de muestras a 64 (el tamaño que usa el dashboard con fftSize 128) conservando picos. */
function to64(buf, out) { const step = buf.length / 64; for (let i = 0; i < 64; i++) { let m = 128, d = 0; for (let j = Math.floor(i * step); j < Math.floor((i + 1) * step); j++) { const dd = Math.abs(buf[j] - 128); if (dd > d) { d = dd; m = buf[j]; } } out[i] = m; } return out; }

export class MicrophoneInput extends EventTarget {
  /** @param {{vad?: object, record?: boolean, pollMs?: number, constraints?: MediaTrackConstraints}} o */
  constructor({ vad = {}, record = true, pollMs = 20, constraints = { echoCancellation: true, noiseSuppression: true, autoGainControl: true } } = {}) {
    super();
    this.vad = new VoiceActivityDetector(vad); this.record = record; this.pollMs = pollMs; this.constraints = constraints;
    this.status = "stopped"; this.level = 0; this.samples = new Uint8Array(64).fill(128); this.buf = new Uint8Array(1024);
  }
  _set(status, detail = {}) { this.status = status; if (detail.message) this.lastMessage = detail.message; this.dispatchEvent(new CustomEvent("status", { detail: { status, ...detail } })); }

  /** Abre el micrófono. Nunca lanza: sin permiso → "denied", sin API → "unsupported". */
  async start() {
    if (this.status === "running") return true;
    if (!navigator.mediaDevices?.getUserMedia) { this._set("unsupported", { message: "El navegador no permite usar el micrófono (getUserMedia)." }); return false; }
    try { this.stream = await navigator.mediaDevices.getUserMedia({ audio: this.constraints, video: false }); }
    catch (err) { this._set("denied", { message: `Sin acceso al micrófono: ${err.name || ""} ${err.message || ""}`.trim() }); return false; }
    this.ctx = new (window.AudioContext || window.webkitAudioContext)();
    await this.ctx.resume().catch(() => {});
    this.source = this.ctx.createMediaStreamSource(this.stream);
    this.analyser = this.ctx.createAnalyser(); this.analyser.fftSize = 1024; this.buf = new Uint8Array(this.analyser.fftSize);
    this.source.connect(this.analyser);                 // nunca a destination: no queremos oír nuestro propio micrófono
    this.chunks = [];
    if (this.record && window.MediaRecorder) {
      this.recorder = new MediaRecorder(this.stream);
      this.recorder.ondataavailable = e => { if (e.data?.size) this.chunks.push(e.data); };
      this.recorder.start(250);
    }
    this.vad.reset(); this.t0 = performance.now();
    this.timer = setInterval(() => this.poll(), this.pollMs);
    this._set("running");
    return true;
  }

  poll(tMs = performance.now()) {
    if (!this.analyser) return;
    this.analyser.getByteTimeDomainData(this.buf);
    to64(this.buf, this.samples);
    this.level = peakOf(this.buf);
    this.dispatchEvent(new CustomEvent("level", { detail: { level: this.level } }));
    const ev = this.vad.process(this.level, tMs);
    if (ev === "start") this.dispatchEvent(new CustomEvent("speechstart", { detail: { t: tMs - this.t0 } }));
    if (ev === "end") {
      const durationMs = this.vad.lastAbove - this.vad.startedAt;
      this.dispatchEvent(new CustomEvent("speechend", { detail: { t: tMs - this.t0, durationMs } }));
    }
  }

  /** Muestras (64, centro 128) para avatar.setAudioSamples. */
  getSamples() { return this.samples; }

  /** Detiene y devuelve lo grabado (Blob) si se pidió grabar. */
  async stop() {
    clearInterval(this.timer); this.timer = null;
    let blob = null;
    if (this.recorder && this.recorder.state !== "inactive") {
      blob = await new Promise(res => { this.recorder.onstop = () => res(new Blob(this.chunks, { type: this.recorder.mimeType || "audio/webm" })); this.recorder.stop(); });
    }
    this.recorder = null;
    if (this.stream) for (const t of this.stream.getTracks()) t.stop();
    this.stream = null; this.source?.disconnect(); this.source = null; this.analyser = null;
    await this.ctx?.close().catch(() => {}); this.ctx = null;
    this.level = 0; this.samples.fill(128);
    if (this.status === "running") this._set("stopped");
    return blob;
  }
}

export class SpeechOutput extends EventTarget {
  constructor() {
    super();
    this.audio = null; this.ctx = null; this.analyser = null; this.buf = new Uint8Array(1024); this.samples = new Uint8Array(64).fill(128);
    this.playing = false; this.level = 0;
  }
  /** Crea el grafo de audio (llamar en un gesto del usuario si el navegador lo exige). */
  unlock() {
    if (this.ctx) { this.ctx.resume().catch(() => {}); return; }
    this.audio = new Audio(); this.audio.preload = "auto"; this.audio.hidden = true; document.body.appendChild(this.audio);
    this.ctx = new (window.AudioContext || window.webkitAudioContext)();
    const src = this.ctx.createMediaElementSource(this.audio);   // sólo una vez por elemento: por eso se reutiliza
    this.analyser = this.ctx.createAnalyser(); this.analyser.fftSize = 1024; this.buf = new Uint8Array(1024);
    src.connect(this.analyser); this.analyser.connect(this.ctx.destination);
    this.ctx.resume().catch(() => {});
  }
  /** Reproduce una URL, Blob o ArrayBuffer. Resuelve al terminar. Eventos "start" (sonando) y "end". */
  async play(src) {
    this.unlock();
    if (this.playing) this.stop();
    let url = src, revoke = null;
    if (src instanceof Blob || src instanceof ArrayBuffer) { url = URL.createObjectURL(src instanceof Blob ? src : new Blob([src])); revoke = url; }
    await this.ctx.resume().catch(() => {});
    this.analysisAvailable = this.ctx.state === "running";
    return new Promise((resolve) => {
      const a = this.audio;
      const finish = (reason) => {
        a.onended = a.onerror = a.onplaying = null;
        if (revoke) URL.revokeObjectURL(revoke);
        const was = this.playing; this.playing = false; this.level = 0; this.samples.fill(128);
        if (was || reason === "error") this.dispatchEvent(new CustomEvent("end", { detail: { reason } }));
        resolve(reason);
      };
      a.onplaying = () => { if (!this.playing) { this.playing = true; this.dispatchEvent(new CustomEvent("start", { detail: { duration: a.duration } })); } };
      a.onended = () => finish("ended");
      a.onerror = () => finish("error");
      this._finish = finish;
      a.src = url;
      a.play().catch(err => { this.lastError = err.message; finish("error"); });
    });
  }
  /** Analiza el audio que suena (llamar por frame). */
  poll() {
    if (!this.playing || !this.analyser) return;
    this.analyser.getByteTimeDomainData(this.buf); to64(this.buf, this.samples); this.level = peakOf(this.buf);
  }
  getSamples() { this.poll(); return this.samples; }
  stop() { if (!this.audio) return; this.audio.pause(); this.audio.currentTime = 0; this._finish?.("stopped"); }
  dispose() { this.stop(); this.audio?.remove(); this.ctx?.close().catch(() => {}); this.audio = this.ctx = this.analyser = null; }
}
