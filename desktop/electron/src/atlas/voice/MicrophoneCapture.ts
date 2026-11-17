// Captura continua del micrófono en tramas PCM de 20 ms a 16 kHz.
//
// Un AudioWorklet entrega el audio crudo (sin pasar por MediaRecorder ni por un
// códec), así el detector de voz trabaja en tiempo real y lo que se manda al
// backend es WAV PCM16 que Whisper lee sin decodificar.

import { FrameAssembler, SPEECH_SAMPLE_RATE, StreamingResampler } from "./pcm.ts";

const WORKLET_SOURCE = `
class AtlasCaptureProcessor extends AudioWorkletProcessor {
  process(inputs) {
    const channel = inputs[0] && inputs[0][0];
    if (channel) this.port.postMessage(channel.slice(0));
    return true;
  }
}
registerProcessor("atlas-capture", AtlasCaptureProcessor);
`;

export type CaptureOptions = {
  frameSize: number;
  onFrame: (frame: Float32Array) => void;
  /** El micrófono se desconectó o el sistema lo cortó. */
  onEnded: () => void;
};

export function microphoneErrorMessage(error: unknown): string {
  const name = error instanceof DOMException ? error.name : "";
  if (name === "NotAllowedError" || name === "SecurityError") return "Permiso de microfono denegado.";
  if (name === "NotFoundError" || name === "OverconstrainedError") return "No se encontro ningun microfono.";
  if (name === "NotReadableError") return "El microfono esta en uso o no responde.";
  return `No se pudo abrir el microfono: ${error instanceof Error ? error.message : String(error)}`;
}

export class MicrophoneCapture {
  private readonly options: CaptureOptions;
  private stream: MediaStream | null = null;
  private context: AudioContext | null = null;
  private node: AudioWorkletNode | null = null;
  private opening: Promise<MediaStream> | null = null;

  constructor(options: CaptureOptions) {
    this.options = options;
  }

  get open(): boolean {
    return this.stream !== null;
  }

  get mediaStream(): MediaStream | null {
    return this.stream;
  }

  /** Abre el micrófono (una sola vez aunque se llame varias). Lanza con el
      error de getUserMedia para que quien llama muestre el mensaje adecuado. */
  start(): Promise<MediaStream> {
    if (this.stream) return Promise.resolve(this.stream);
    this.opening ??= this.openStream().finally(() => {
      this.opening = null;
    });
    return this.opening;
  }

  stop(): void {
    const stream = this.stream;
    this.stream = null;
    this.node?.port.close();
    this.node?.disconnect();
    this.node = null;
    stream?.getTracks().forEach((track) => track.stop());
    void this.context?.close().catch(() => undefined);
    this.context = null;
  }

  /** Pitido breve en la salida (confirmación de "Atlas"). */
  chime(): void {
    const context = this.context;
    if (!context) return;
    const now = context.currentTime;
    const gain = context.createGain();
    gain.gain.setValueAtTime(0.0001, now);
    gain.gain.exponentialRampToValueAtTime(0.08, now + 0.02);
    gain.gain.exponentialRampToValueAtTime(0.0001, now + 0.22);
    gain.connect(context.destination);
    for (const [frequency, start] of [[660, 0], [990, 0.07]] as const) {
      const oscillator = context.createOscillator();
      oscillator.frequency.value = frequency;
      oscillator.connect(gain);
      oscillator.start(now + start);
      oscillator.stop(now + 0.24);
    }
  }

  private async openStream(): Promise<MediaStream> {
    const stream = await navigator.mediaDevices.getUserMedia({
      // El cancelador de eco evita que ATLAS se oiga a sí mismo por los
      // altavoces; la supresión de ruido ayuda al detector de voz.
      audio: { channelCount: 1, echoCancellation: true, noiseSuppression: true, autoGainControl: true },
    });
    try {
      await this.connect(stream);
    } catch (error) {
      stream.getTracks().forEach((track) => track.stop());
      this.stop();
      throw error;
    }
    this.stream = stream;
    stream.getAudioTracks()[0]?.addEventListener("ended", () => {
      if (this.stream !== stream) return;
      this.stop();
      this.options.onEnded();
    });
    return stream;
  }

  private async connect(stream: MediaStream): Promise<void> {
    // Pedir el contexto ya a 16 kHz: Chromium remuestrea el micrófono. Si el
    // sistema no lo admite, se usa la frecuencia nativa y se remuestrea aquí.
    let context: AudioContext;
    let source: MediaStreamAudioSourceNode;
    try {
      context = new AudioContext({ sampleRate: SPEECH_SAMPLE_RATE });
      source = context.createMediaStreamSource(stream);
    } catch {
      context = new AudioContext();
      source = context.createMediaStreamSource(stream);
    }
    this.context = context;
    const url = URL.createObjectURL(new Blob([WORKLET_SOURCE], { type: "application/javascript" }));
    try {
      await context.audioWorklet.addModule(url);
    } finally {
      URL.revokeObjectURL(url);
    }
    if (context.state === "suspended") await context.resume();

    const resampler = new StreamingResampler(context.sampleRate, SPEECH_SAMPLE_RATE);
    const assembler = new FrameAssembler(this.options.frameSize);
    const node = new AudioWorkletNode(context, "atlas-capture", { numberOfInputs: 1, numberOfOutputs: 1, channelCount: 1 });
    node.port.onmessage = (event: MessageEvent<Float32Array>) => {
      assembler.push(resampler.process(event.data), this.options.onFrame);
    };
    // El nodo tiene que estar conectado a la salida para que el grafo lo
    // procese; la ganancia 0 evita oír el micrófono.
    const mute = context.createGain();
    mute.gain.value = 0;
    source.connect(node);
    node.connect(mute);
    mute.connect(context.destination);
    this.node = node;
  }
}
