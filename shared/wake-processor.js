/* AudioWorklet del wake word — corre en el hilo de audio, no en el principal.
 *
 * Solo reenvía las muestras crudas al hilo principal; toda la lógica (buffer
 * deslizante, filtro de energía, transcripción) vive en wake-word.js. Se usa
 * AudioWorklet y no ScriptProcessorNode porque esto queda corriendo de forma
 * continua mientras la app está abierta: hacerlo en el hilo principal
 * competiría con el renderizado de la interfaz.
 */
class WakeProcessor extends AudioWorkletProcessor {
  process(inputs) {
    const channel = inputs[0] && inputs[0][0];
    if (channel && channel.length) {
      // Copia obligatoria: el buffer que entrega el worklet se reutiliza en
      // el siguiente ciclo, así que mandarlo tal cual corrompe los datos.
      this.port.postMessage(new Float32Array(channel));
    }
    return true; // mantener vivo el nodo
  }
}

registerProcessor("wake-processor", WakeProcessor);
