import 'dart:math' as math;
import 'dart:typed_data';

/// WAV PCM16 mono a partir de muestras (lo que espera /voice/transcribe).
Uint8List wavFromPcm16(Int16List samples, {int sampleRate = 16000}) {
  final dataBytes = samples.length * 2;
  final bytes = ByteData(44 + dataBytes);
  void ascii(int offset, String text) {
    for (var i = 0; i < text.length; i++) {
      bytes.setUint8(offset + i, text.codeUnitAt(i));
    }
  }

  ascii(0, 'RIFF');
  bytes.setUint32(4, 36 + dataBytes, Endian.little);
  ascii(8, 'WAVE');
  ascii(12, 'fmt ');
  bytes.setUint32(16, 16, Endian.little);
  bytes.setUint16(20, 1, Endian.little); // PCM
  bytes.setUint16(22, 1, Endian.little); // mono
  bytes.setUint32(24, sampleRate, Endian.little);
  bytes.setUint32(28, sampleRate * 2, Endian.little);
  bytes.setUint16(32, 2, Endian.little);
  bytes.setUint16(34, 16, Endian.little);
  ascii(36, 'data');
  bytes.setUint32(40, dataBytes, Endian.little);
  for (var i = 0; i < samples.length; i++) {
    bytes.setInt16(44 + i * 2, samples[i], Endian.little);
  }
  return bytes.buffer.asUint8List();
}

/// Volumen (0..1) cada `windowMs` de un WAV PCM16: anima el núcleo al ritmo de
/// la voz de ATLAS mientras habla. Lista vacía si el WAV no es PCM16.
List<double> wavEnvelope(Uint8List wav, {int windowMs = 50}) {
  if (wav.length < 44) return const [];
  final data = ByteData.sublistView(wav);
  var offset = 12;
  int? sampleRate, channels, bits;
  int? dataStart, dataLength;
  while (offset + 8 <= wav.length) {
    final id = String.fromCharCodes(wav.sublist(offset, offset + 4));
    final size = data.getUint32(offset + 4, Endian.little);
    if (id == 'fmt ' && offset + 24 <= wav.length) {
      channels = data.getUint16(offset + 10, Endian.little);
      sampleRate = data.getUint32(offset + 12, Endian.little);
      bits = data.getUint16(offset + 22, Endian.little);
    } else if (id == 'data') {
      dataStart = offset + 8;
      dataLength = math.min(size, wav.length - dataStart);
      break;
    }
    offset += 8 + size + (size.isOdd ? 1 : 0);
  }
  if (sampleRate == null || channels == null || bits != 16 || dataStart == null || dataLength == null) return const [];
  final frameBytes = 2 * channels;
  final window = math.max(1, sampleRate * windowMs ~/ 1000) * frameBytes;
  final levels = <double>[];
  for (var start = 0; start + frameBytes <= dataLength; start += window) {
    final end = math.min(start + window, dataLength);
    var sum = 0.0;
    var n = 0;
    for (var i = start; i + 1 < end; i += frameBytes) {
      final s = data.getInt16(dataStart + i, Endian.little);
      sum += s * s;
      n++;
    }
    final rms = n == 0 ? 0 : math.sqrt(sum / n) / 32768;
    levels.add((rms * 4).clamp(0, 1).toDouble());
  }
  return levels;
}

/// Duración de un WAV PCM16 en ms (0 si no se puede leer).
int wavDurationMs(Uint8List wav) => wavEnvelope(wav, windowMs: 10).length * 10;

/// Sonido corto de "te escucho" (dos tonos ascendentes, como el del escritorio).
Uint8List chimeWav({int sampleRate = 22050}) {
  final samples = <int>[];
  for (final (freq, ms) in [(880.0, 90), (1320.0, 120)]) {
    final n = sampleRate * ms ~/ 1000;
    for (var i = 0; i < n; i++) {
      final fade = math.min(1.0, math.min(i, n - i) / (sampleRate * 0.01));
      samples.add((math.sin(2 * math.pi * freq * i / sampleRate) * 0.28 * fade * 32767).round());
    }
  }
  return wavFromPcm16(Int16List.fromList(samples), sampleRate: sampleRate);
}
