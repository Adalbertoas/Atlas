import 'dart:math' as math;
import 'dart:typed_data';

import 'package:atlas_tablet/core/segmenter.dart';
import 'package:atlas_tablet/core/wake_word.dart';
import 'package:atlas_tablet/core/wav.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  // Mismos casos que desktop/electron/src/atlas/voice/voice.test.ts.
  group('palabra de activación', () {
    test('detecta "Atlas" al principio y separa el pedido', () {
      expect(detectWakeWord('Atlas, ¿qué hora es?'), isA<WakeMatch>().having((m) => m.command, 'command', '¿qué hora es?'));
      final alone = detectWakeWord('Atlas.');
      expect((alone.detected, alone.command), (true, ''));
      expect(detectWakeWord('Oye Atlas, apaga la luz').command, 'apaga la luz');
      expect(detectWakeWord('hola, atlas: pon música').command, 'pon música');
      expect(detectWakeWord('ÁTLAS abre el navegador').command, 'abre el navegador');
    });

    test('tolera cómo Whisper oye mal el nombre', () {
      for (final heard in ['Hatlas, hola', 'Adlas, hola', 'At las, hola', 'Atla, hola', 'Attlas hola', 'Atlaz hola']) {
        expect(detectWakeWord(heard).detected, isTrue, reason: heard);
      }
    });

    test('no se activa con Atlas a mitad de frase ni con palabras parecidas', () {
      for (final heard in ['el atlas de geografía está en la mesa', 'las aulas están vacías', 'altas montañas', 'alas de mariposa', 'atrás', '', '  ']) {
        expect(detectWakeWord(heard).detected, isFalse, reason: heard);
      }
    });

    test('levenshtein', () {
      expect(levenshtein('atlas', 'atlas'), 0);
      expect(levenshtein('atlas', 'adlas'), 1);
      expect(levenshtein('atlas', 'altas'), 2);
    });

    test('descarta alucinaciones típicas de Whisper', () {
      for (final junk in ['¡Gracias por ver el video!', 'Subtítulos realizados por la comunidad de Amara.org', '¡Adiós!', '...', 'Música', '']) {
        expect(cleanTranscript(junk), '', reason: junk);
      }
      expect(cleanTranscript('  Atlas,   gracias por todo '), 'Atlas, gracias por todo');
    });
  });

  group('detector de voz', () {
    Uint8List pcm(double seconds, double amplitude, {double freq = 220}) {
      final n = (16000 * seconds).round();
      final data = ByteData(n * 2);
      final random = math.Random(1);
      for (var i = 0; i < n; i++) {
        final noise = (random.nextDouble() - .5) * 60; // ruido de fondo leve
        final s = amplitude * math.sin(2 * math.pi * freq * i / 16000) + noise;
        data.setInt16(i * 2, s.round().clamp(-32768, 32767), Endian.little);
      }
      return data.buffer.asUint8List();
    }

    test('corta una frase entre silencios e incluye el audio previo', () {
      final segmenter = SpeechSegmenter();
      final utterances = <(int, int)>[];
      segmenter.onUtterance = (samples, voicedMs) => utterances.add((samples.length, voicedMs));
      segmenter.add(pcm(1.5, 0)); // silencio: aprende el piso de ruido
      segmenter.add(pcm(1.0, 8000)); // voz
      segmenter.add(pcm(1.0, 0)); // silencio que cierra la frase
      expect(utterances, hasLength(1));
      final (length, voicedMs) = utterances.single;
      expect(voicedMs, inInclusiveRange(900, 1100));
      // ~1 s de voz + pre-roll + silencio final hasta el corte.
      expect(length / 16000, inInclusiveRange(1.5, 2.2));
    });

    test('el ruido constante no dispara frases', () {
      final segmenter = SpeechSegmenter();
      var count = 0;
      segmenter.onUtterance = (_, _) => count++;
      segmenter.add(pcm(6, 0));
      expect(count, 0);
    });

    test('un ruido fuerte y constante se aprende como fondo (no frases sin fin)', () {
      final segmenter = SpeechSegmenter();
      var count = 0;
      segmenter.onUtterance = (_, _) => count++;
      segmenter.add(Uint8List(16000)); // medio segundo de ceros al abrir el micrófono
      segmenter.add(pcm(12, 400, freq: 120)); // ventilador o tele: ~ -38 dB sin pausas
      expect(count, lessThanOrEqualTo(1));
      expect(segmenter.inSpeech, isFalse);
      expect(segmenter.noiseFloorDb, greaterThan(-45));
    });

    test('flush envía la frase en curso', () {
      final segmenter = SpeechSegmenter();
      var count = 0;
      segmenter.onUtterance = (_, _) => count++;
      segmenter.add(pcm(1.5, 0));
      segmenter.add(pcm(0.6, 8000));
      expect(segmenter.inSpeech, isTrue);
      expect(segmenter.flush(), isTrue);
      expect(count, 1);
      expect(segmenter.flush(), isFalse);
    });

    test('bytes que llegan partidos en cualquier punto', () {
      final segmenter = SpeechSegmenter();
      var count = 0;
      segmenter.onUtterance = (_, _) => count++;
      final audio = Uint8List.fromList([...pcm(1.5, 0), ...pcm(1, 8000), ...pcm(1, 0)]);
      for (var i = 0; i < audio.length; i += 777) {
        segmenter.add(audio.sublist(i, math.min(i + 777, audio.length)));
      }
      expect(count, 1);
    });
  });

  group('wav', () {
    test('el WAV generado tiene cabecera y duración correctas', () {
      final wav = wavFromPcm16(Int16List(16000));
      expect(String.fromCharCodes(wav.sublist(0, 4)), 'RIFF');
      expect(String.fromCharCodes(wav.sublist(8, 12)), 'WAVE');
      expect(wav.length, 44 + 32000);
      expect(wavDurationMs(wav), 1000);
    });

    test('la envolvente sigue el volumen', () {
      final loud = Int16List.fromList(List.generate(8000, (i) => (12000 * math.sin(i / 5)).round()));
      final env = wavEnvelope(wavFromPcm16(Int16List.fromList([...Int16List(8000), ...loud])));
      expect(env.first, lessThan(.05));
      expect(env.last, greaterThan(.5));
    });

    test('el sonido de activación es un WAV válido y corto', () {
      final chime = chimeWav();
      expect(String.fromCharCodes(chime.sublist(0, 4)), 'RIFF');
      expect(wavDurationMs(chime), inInclusiveRange(150, 300));
    });
  });
}
