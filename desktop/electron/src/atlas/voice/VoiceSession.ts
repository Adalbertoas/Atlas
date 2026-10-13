// Flujo de voz del cliente Electron: grabar → transcribir → (chat) → hablar.
// Usa los endpoints de voz que ya expone el backend, a través del puente IPC.
// Una sola captura de micrófono alimenta la grabación y el analizador.

import type { AudioAnalyzer } from "../audio-reactive/AudioAnalyzer.ts";

export type VoicePhase = "idle" | "recording" | "transcribing" | "synthesizing" | "speaking";

export type VoiceTransport = (channel: string, input?: unknown) => Promise<unknown>;

export type VoiceSessionOptions = {
  analyzer: AudioAnalyzer;
  transport: VoiceTransport;
  onPhase: (phase: VoicePhase) => void;
  onTranscript: (text: string) => void;
  onError: (message: string) => void;
};

function microphoneErrorMessage(error: unknown): string {
  const name = error instanceof DOMException ? error.name : "";
  if (name === "NotAllowedError" || name === "SecurityError") return "Permiso de microfono denegado.";
  if (name === "NotFoundError" || name === "OverconstrainedError") return "No se encontro ningun microfono.";
  if (name === "NotReadableError") return "El microfono esta en uso o no responde.";
  return `No se pudo abrir el microfono: ${error instanceof Error ? error.message : String(error)}`;
}

export class VoiceSession {
  private readonly options: VoiceSessionOptions;
  private phase: VoicePhase = "idle";
  private stream: MediaStream | null = null;
  private recorder: MediaRecorder | null = null;
  private chunks: Blob[] = [];
  private discard = false;
  private speechToken = 0;

  constructor(options: VoiceSessionOptions) {
    this.options = options;
  }

  get currentPhase(): VoicePhase {
    return this.phase;
  }

  get recording(): boolean {
    return this.phase === "recording";
  }

  async startRecording(): Promise<void> {
    if (this.phase === "recording" || this.phase === "transcribing") return;
    this.stopSpeaking();
    let stream: MediaStream;
    try {
      stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    } catch (error) {
      this.options.onError(microphoneErrorMessage(error));
      return;
    }
    this.stream = stream;
    this.chunks = [];
    this.discard = false;
    // Micrófono desenchufado o dispositivo de entrada cambiado a mitad de frase.
    stream.getAudioTracks()[0]?.addEventListener("ended", () => {
      if (this.stream !== stream) return;
      this.cancelRecording();
      this.options.onError("El microfono se desconecto.");
    });

    const recorder = new MediaRecorder(stream);
    recorder.ondataavailable = (event) => {
      if (event.data.size) this.chunks.push(event.data);
    };
    recorder.onstop = () => void this.finishRecording(recorder.mimeType || "audio/webm");
    this.recorder = recorder;
    this.options.analyzer.attachMicrophone(stream);
    recorder.start();
    this.setPhase("recording");
  }

  /** Termina la grabación y la envía a transcribir. */
  stopRecording(): void {
    if (this.recorder?.state === "recording") this.recorder.stop();
    this.releaseMicrophone();
  }

  /** Termina la grabación descartando el audio. */
  cancelRecording(): void {
    this.discard = true;
    if (this.recorder?.state === "recording") this.recorder.stop();
    this.releaseMicrophone();
    if (this.phase === "recording") this.setPhase("idle");
  }

  /** Sintetiza y reproduce `text` con la voz del backend. No lanza: un fallo de
      voz no debe afectar a la respuesta de texto, que ya está en pantalla. */
  async speak(text: string): Promise<void> {
    const clean = text.trim();
    if (!clean || this.phase === "recording") return;
    const token = ++this.speechToken;
    this.options.analyzer.stopPlayback();
    this.setPhase("synthesizing");
    try {
      const audio = await this.options.transport("atlas:speak", { text: clean });
      if (token !== this.speechToken) return;
      const bytes = audio instanceof Uint8Array ? audio : new Uint8Array(audio as ArrayBuffer);
      if (!bytes.byteLength) throw new Error("El backend no devolvio audio.");
      this.setPhase("speaking");
      // decodeAudioData se queda con el buffer: se le pasa una copia exacta.
      await this.options.analyzer.play(bytes.buffer.slice(bytes.byteOffset, bytes.byteOffset + bytes.byteLength) as ArrayBuffer);
    } catch (error) {
      if (token === this.speechToken) this.options.onError(`No se pudo reproducir la voz de ATLAS: ${error instanceof Error ? error.message : String(error)}`);
    } finally {
      if (token === this.speechToken && (this.phase === "speaking" || this.phase === "synthesizing")) this.setPhase("idle");
    }
  }

  stopSpeaking(): void {
    this.speechToken += 1;
    this.options.analyzer.stopPlayback();
    if (this.phase === "speaking" || this.phase === "synthesizing") this.setPhase("idle");
  }

  dispose(): void {
    this.cancelRecording();
    this.stopSpeaking();
  }

  private releaseMicrophone(): void {
    this.options.analyzer.detachMicrophone();
    this.stream?.getTracks().forEach((track) => track.stop());
    this.stream = null;
  }

  private async finishRecording(mimeType: string): Promise<void> {
    this.recorder = null;
    const chunks = this.chunks;
    this.chunks = [];
    if (this.discard) return;
    const blob = new Blob(chunks, { type: mimeType });
    if (!blob.size) {
      this.setPhase("idle");
      return;
    }
    this.setPhase("transcribing");
    try {
      const result = (await this.options.transport("atlas:transcribe", { audio: new Uint8Array(await blob.arrayBuffer()), mimeType })) as { text?: string };
      this.setPhase("idle");
      const text = (result.text ?? "").trim();
      if (text) this.options.onTranscript(text);
      else this.options.onError("No se entendio ninguna palabra en la grabacion.");
    } catch (error) {
      this.setPhase("idle");
      this.options.onError(`No se pudo transcribir el audio: ${error instanceof Error ? error.message : String(error)}`);
    }
  }

  private setPhase(phase: VoicePhase): void {
    if (phase === this.phase) return;
    this.phase = phase;
    this.options.onPhase(phase);
  }
}
