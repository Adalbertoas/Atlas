import 'dart:math' as math;
import 'dart:typed_data';

/// Corta el audio del micrófono en frases: detecta voz por volumen sobre un
/// piso de ruido que se adapta solo (el modo "detección por volumen" del
/// escritorio, SpeechSegmenter.ts, con sus mismos valores por defecto).
class SpeechSegmenter {
  SpeechSegmenter({
    this.sampleRate = 16000,
    this.frameMs = 20,
    this.preRollMs = 300,
    this.minSpeechMs = 120,
    this.maxUtteranceMs = 15000,
    this.minLevelDb = -50,
    this.noiseWindowMs = 3000,
    this.initialNoiseDb = -65,
    this.noiseRiseDbPerSecond = 6,
  }) : noiseFloorDb = initialNoiseDb;

  final int sampleRate;
  final int frameMs;
  final int preRollMs;
  final int minSpeechMs;
  final int maxUtteranceMs;
  final double minLevelDb;
  final int noiseWindowMs;
  final double initialNoiseDb;
  final double noiseRiseDbPerSecond;

  /// 0 (estricta) … 1 (capta voz baja).
  double sensitivity = 0.5;

  /// Silencio que cierra una frase: más corto en reposo, más largo con un pedido.
  int endSilenceMs = 700;

  /// Frase completa (PCM16 mono) y cuánta voz tenía en ms.
  void Function(Int16List samples, int voicedMs)? onUtterance;
  void Function()? onSpeechStart;

  double noiseFloorDb;
  double levelDb = -90;
  bool inSpeech = false;

  int get _frameSamples => sampleRate * frameMs ~/ 1000;
  final _pending = BytesBuilder(copy: false);
  final _preRoll = <Int16List>[];
  final _utterance = <Int16List>[];
  final _noiseLevels = <double>[];
  int _voicedRun = 0;
  int _voicedMs = 0;
  int _silenceMs = 0;
  int _framesSinceNoise = 0;

  /// Margen sobre el ruido según la sensibilidad (igual que el escritorio).
  double get marginDb => 18 - sensitivity.clamp(0, 1) * 12;
  double get thresholdDb => math.max(noiseFloorDb + marginDb, minLevelDb);

  /// Agrega bytes PCM16 little-endian tal como llegan del micrófono.
  void add(Uint8List bytes) {
    _pending.add(bytes);
    final frameBytes = _frameSamples * 2;
    if (_pending.length < frameBytes) return;
    final all = _pending.takeBytes();
    var offset = 0;
    while (all.length - offset >= frameBytes) {
      final frame = Int16List(_frameSamples);
      final view = ByteData.sublistView(all, offset, offset + frameBytes);
      for (var i = 0; i < _frameSamples; i++) {
        frame[i] = view.getInt16(i * 2, Endian.little);
      }
      _process(frame);
      offset += frameBytes;
    }
    if (offset < all.length) _pending.add(all.sublist(offset));
  }

  void _process(Int16List frame) {
    var sum = 0.0;
    for (final s in frame) {
      sum += s * s;
    }
    final rms = math.sqrt(sum / frame.length);
    // Ceros exactos: el micrófono todavía no entrega audio (pasa al abrirlo).
    // No es silencio real; si se aprendiera, todo el ruido de la sala pasaría por voz.
    if (rms < 2) return;
    levelDb = 20 * math.log(rms / 32768) / math.ln10;
    // El piso se sigue también durante la "voz": un ruido constante (ventilador,
    // tele) sube el piso hasta dejar de contar como voz. Las pausas entre
    // palabras mantienen el percentil bajo cuando sí es alguien hablando.
    _trackNoise(levelDb);
    final voiced = levelDb >= thresholdDb;

    if (!inSpeech) {
      _preRoll.add(frame);
      final maxFrames = (preRollMs + minSpeechMs) ~/ frameMs + 1;
      while (_preRoll.length > maxFrames) {
        _preRoll.removeAt(0);
      }
      _voicedRun = voiced ? _voicedRun + 1 : 0;
      if (_voicedRun * frameMs >= minSpeechMs) {
        inSpeech = true;
        _utterance
          ..clear()
          ..addAll(_preRoll);
        _preRoll.clear();
        _voicedMs = _voicedRun * frameMs;
        _silenceMs = 0;
        onSpeechStart?.call();
      }
      return;
    }

    _utterance.add(frame);
    if (voiced) {
      _voicedMs += frameMs;
      _silenceMs = 0;
    } else {
      _silenceMs += frameMs;
    }
    if (_silenceMs >= endSilenceMs || _utterance.length * frameMs >= maxUtteranceMs) _emit();
  }

  /// Piso de ruido = percentil 10 de los últimos segundos; sube despacio (la
  /// voz no lo arrastra) y baja de golpe (si se hizo silencio, se nota enseguida).
  void _trackNoise(double db) {
    _noiseLevels.add(db);
    final window = noiseWindowMs ~/ frameMs;
    if (_noiseLevels.length > window) _noiseLevels.removeAt(0);
    if (++_framesSinceNoise < 10) return;
    final elapsedS = _framesSinceNoise * frameMs / 1000;
    _framesSinceNoise = 0;
    final sorted = List<double>.of(_noiseLevels)..sort();
    final p10 = math.max(sorted[(sorted.length * 0.1).floor().clamp(0, sorted.length - 1)], -80.0);
    noiseFloorDb = p10 > noiseFloorDb ? math.min(p10, noiseFloorDb + noiseRiseDbPerSecond * elapsedS) : p10;
  }

  /// Cierra ya la frase en curso (el usuario tocó "enviar"). false si no había voz.
  bool flush() {
    if (!inSpeech) return false;
    _emit();
    return true;
  }

  void _emit() {
    final total = _utterance.fold<int>(0, (n, f) => n + f.length);
    final samples = Int16List(total);
    var offset = 0;
    for (final f in _utterance) {
      samples.setAll(offset, f);
      offset += f.length;
    }
    final voicedMs = _voicedMs;
    _utterance.clear();
    inSpeech = false;
    _voicedRun = 0;
    _voicedMs = 0;
    _silenceMs = 0;
    onUtterance?.call(samples, voicedMs);
  }

  /// Descarta lo que había (después de que ATLAS habló, por ejemplo).
  void reset() {
    _pending.clear();
    _preRoll.clear();
    _utterance.clear();
    inSpeech = false;
    _voicedRun = 0;
    _voicedMs = 0;
    _silenceMs = 0;
  }
}
