/* Wake word para los clientes web (dashboard y PWA móvil).
 *
 * Port de desktop/atlas_desktop/wake_word.py, con la misma estrategia:
 * no hay motor de wake word dedicado (Porcupine pide licencia; openWakeWord
 * no trae modelo en español para esta palabra), así que se reutiliza el
 * Whisper que ya expone el backend en /api/v1/voice/transcribe.
 *
 *   1. Buffer deslizante de audio (no bloques pegados uno tras otro: así la
 *      palabra nunca queda cortada justo en el límite entre dos ventanas).
 *   2. Filtro de energía local y barato — si la ventana está en silencio ni
 *      se manda. Sin esto le pegaríamos a Whisper una vez por segundo las
 *      24 horas.
 *   3. Solo las ventanas con sonido real se transcriben, y se busca la
 *      palabra entre las primeras palabras del texto.
 *
 * Vive en shared/ y no duplicado en cada cliente a propósito: son la misma
 * lógica, y tener dos copias garantiza que en algún momento se
 * desincronicen (ya pasó al renombrar la palabra de activación).
 *
 * Limitación heredada del enfoque: ~1-3 s de latencia y puede confundir la
 * palabra con otras parecidas. Es el mismo compromiso que el escritorio.
 */

const BUFFER_SECONDS = 3.0;       // ventana deslizante que se revisa
const POLL_INTERVAL_MS = 1000;    // cada cuánto se revisa el buffer
// Equivale al umbral RMS de 1000 sobre int16 del cliente de escritorio
// (1000/32768). Ajustado allá tras probar en vivo: el ruido ambiente de una
// habitación llega a ~800 y disparaba transcripciones falsas, porque Whisper
// "alucina" frases sobre ruido de fondo.
const SILENCE_RMS_THRESHOLD = 1000 / 32768;

/** Normaliza tildes: "visión" y "vision" deben matchear igual. */
function stripAccents(text) {
  return text.normalize("NFKD").replace(/[̀-ͯ]/g, "");
}

/** True solo si la palabra aparece entre las primeras palabras del texto,
 *  como cuando alguien te llama por tu nombre al empezar a hablarte. Buscarla
 *  en cualquier parte disparaba falsos positivos con conversaciones de fondo
 *  que la mencionaban de pasada (mismo criterio que el cliente de escritorio). */
export function containsWakeWord(text, wakeWord) {
  const words = (stripAccents(text || "").toLowerCase().match(/[a-zñ]+/g) || []).slice(0, 2);
  return words.includes(stripAccents(wakeWord.toLowerCase()));
}

/** RMS de un bloque de muestras float (-1..1). */
function rms(samples) {
  if (!samples.length) return 0;
  let sum = 0;
  for (let i = 0; i < samples.length; i++) sum += samples[i] * samples[i];
  return Math.sqrt(sum / samples.length);
}

/** Empaqueta muestras float como WAV PCM 16 bits, que es lo que espera
 *  /api/v1/voice/transcribe. Se hace a mano porque MediaRecorder produce
 *  WebM en contenedor: sus fragmentos no son decodificables por separado,
 *  así que no sirven para una ventana deslizante. */
function encodeWav(samples, sampleRate) {
  const buffer = new ArrayBuffer(44 + samples.length * 2);
  const view = new DataView(buffer);
  const writeString = (offset, text) => {
    for (let i = 0; i < text.length; i++) view.setUint8(offset + i, text.charCodeAt(i));
  };

  writeString(0, "RIFF");
  view.setUint32(4, 36 + samples.length * 2, true);
  writeString(8, "WAVE");
  writeString(12, "fmt ");
  view.setUint32(16, 16, true);      // tamaño del bloque fmt
  view.setUint16(20, 1, true);       // PCM sin comprimir
  view.setUint16(22, 1, true);       // mono
  view.setUint32(24, sampleRate, true);
  view.setUint32(28, sampleRate * 2, true); // bytes por segundo
  view.setUint16(32, 2, true);       // alineación de bloque
  view.setUint16(34, 16, true);      // bits por muestra
  writeString(36, "data");
  view.setUint32(40, samples.length * 2, true);

  for (let i = 0; i < samples.length; i++) {
    const clamped = Math.max(-1, Math.min(1, samples[i]));
    view.setInt16(44 + i * 2, clamped < 0 ? clamped * 0x8000 : clamped * 0x7fff, true);
  }
  return new Blob([buffer], { type: "audio/wav" });
}

export class WakeWordEngine {
  /**
   * @param {object} options
   * @param {string} options.workletUrl  ruta a wake-processor.js
   * @param {() => Promise<string>} options.transcribe  recibe un Blob WAV y devuelve el texto
   * @param {string} options.wakeWord    palabra a detectar (la define el backend)
   * @param {() => void} options.onActivated  se llama al detectarla
   * @param {(state: string, detail?: string) => void} [options.onStatus]
   */
  constructor({ workletUrl, transcribe, wakeWord, onActivated, onStatus }) {
    this._workletUrl = workletUrl;
    this._transcribe = transcribe;
    this._wakeWord = wakeWord;
    this._onActivated = onActivated;
    this._onStatus = onStatus || (() => {});

    this._active = false;
    this._paused = false;
    this._stream = null;
    this._context = null;
    this._node = null;
    this._timer = null;
    this._buffer = new Float32Array(0);
    this._maxSamples = 0;
    this._checking = false;
  }

  get isActive() {
    return this._active;
  }

  async start() {
    if (this._active) return;
    try {
      this._stream = await navigator.mediaDevices.getUserMedia({
        audio: { channelCount: 1, echoCancellation: true, noiseSuppression: true },
      });
    } catch (err) {
      this._onStatus("error", `No pude acceder al micrófono: ${err.message}`);
      return;
    }

    try {
      this._context = new (window.AudioContext || window.webkitAudioContext)();
      await this._context.audioWorklet.addModule(this._workletUrl);
    } catch (err) {
      this._onStatus("error", `No pude iniciar la escucha: ${err.message}`);
      this.stop();
      return;
    }

    // No se fuerza 16 kHz: el AudioContext usa la tasa del dispositivo y el
    // WAV se etiqueta con la real. Whisper acepta cualquier tasa, así que
    // remuestrear sería trabajo extra sin ganancia.
    this._maxSamples = Math.floor(this._context.sampleRate * BUFFER_SECONDS);
    this._buffer = new Float32Array(0);

    const source = this._context.createMediaStreamSource(this._stream);
    this._node = new AudioWorkletNode(this._context, "wake-processor");
    this._node.port.onmessage = (event) => this._append(event.data);
    source.connect(this._node);
    // Sin conectar a destination: no queremos oír nuestro propio micrófono.

    this._active = true;
    this._paused = false;
    this._onStatus("listening");
    this._timer = setInterval(() => this._check(), POLL_INTERVAL_MS);
  }

  stop() {
    this._active = false;
    if (this._timer) clearInterval(this._timer);
    this._timer = null;
    if (this._node) {
      this._node.port.onmessage = null;
      this._node.disconnect();
      this._node = null;
    }
    if (this._stream) {
      this._stream.getTracks().forEach((track) => track.stop());
      this._stream = null;
    }
    if (this._context) {
      this._context.close().catch(() => {});
      this._context = null;
    }
    this._buffer = new Float32Array(0);
    this._onStatus("stopped");
  }

  /** Suspende la detección sin soltar el micrófono. Se usa mientras ATLAS
   *  graba el comando o habla: sin esto se escucharía a sí mismo por los
   *  parlantes y volvería a dispararse (mismo problema que resolvió el
   *  cliente de escritorio cerrando su stream). */
  pause() {
    this._paused = true;
    this._buffer = new Float32Array(0);
  }

  resume() {
    this._paused = false;
    this._buffer = new Float32Array(0); // descartar lo captado mientras hablaba
    if (this._active) this._onStatus("listening");
  }

  // ---------- interno ----------

  _append(chunk) {
    if (!this._active || this._paused) return;
    const merged = new Float32Array(this._buffer.length + chunk.length);
    merged.set(this._buffer);
    merged.set(chunk, this._buffer.length);
    // Ventana deslizante: se conservan solo los últimos BUFFER_SECONDS.
    this._buffer = merged.length > this._maxSamples
      ? merged.slice(merged.length - this._maxSamples)
      : merged;
  }

  async _check() {
    if (!this._active || this._paused || this._checking) return;
    const samples = this._buffer;
    if (samples.length < this._maxSamples / 2) return; // todavía no hay ventana suficiente

    // Filtro de energía local: lo barato primero. Sin esto le pegaríamos a
    // Whisper una vez por segundo aunque no haya nadie hablando.
    if (rms(samples) < SILENCE_RMS_THRESHOLD) return;

    this._checking = true;
    try {
      const text = await this._transcribe(encodeWav(samples, this._context.sampleRate));
      if (!this._active || this._paused) return;
      if (containsWakeWord(text, this._wakeWord)) {
        this._buffer = new Float32Array(0);
        this._onActivated();
      }
    } catch {
      /* un fallo de transcripción no debe matar el loop de escucha */
    } finally {
      this._checking = false;
    }
  }
}
