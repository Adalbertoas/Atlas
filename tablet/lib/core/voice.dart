import 'dart:async';

import 'package:audioplayers/audioplayers.dart';
import 'package:flutter/foundation.dart';
import 'package:record/record.dart';

import 'wav.dart';

/// Micrófono en streaming (PCM16 16 kHz mono, lo que espera Whisper) y
/// reproducción de la voz de ATLAS con su nivel, para animar el núcleo.
class VoiceService {
  final _recorder = AudioRecorder();
  final _player = AudioPlayer();
  final _chimePlayer = AudioPlayer();
  final _chime = chimeWav();
  StreamSubscription<Uint8List>? _mic;
  Completer<void>? _speaking;
  Timer? _levelTimer;

  /// Volumen de la voz de ATLAS mientras habla (0..1).
  final speakingLevel = ValueNotifier<double>(0);
  final isSpeaking = ValueNotifier<bool>(false);

  bool get micOn => _mic != null;

  Future<bool> hasPermission() => _recorder.hasPermission();

  /// false si el usuario no dio permiso de micrófono.
  Future<bool> startMic(void Function(Uint8List bytes) onData, {void Function(Object error)? onError}) async {
    if (_mic != null) return true;
    if (!await _recorder.hasPermission()) return false;
    final stream = await _recorder.startStream(const RecordConfig(
      encoder: AudioEncoder.pcm16bits,
      sampleRate: 16000,
      numChannels: 1,
      // El filtro de Android pensado para reconocimiento de voz.
      androidConfig: AndroidRecordConfig(audioSource: AndroidAudioSource.voiceRecognition),
    ));
    _mic = stream.listen(onData, onError: onError, cancelOnError: false);
    return true;
  }

  Future<void> stopMic() async {
    await _mic?.cancel();
    _mic = null;
    if (await _recorder.isRecording()) await _recorder.stop();
  }

  /// Reproduce el WAV y termina cuando ATLAS terminó de hablar.
  Future<void> speak(Uint8List wav) async {
    await stopSpeaking();
    final envelope = wavEnvelope(wav);
    final done = _speaking = Completer<void>();
    final clock = Stopwatch();
    final sub = _player.onPlayerComplete.listen((_) {
      if (!done.isCompleted) done.complete();
    });
    isSpeaking.value = true;
    try {
      await _player.play(BytesSource(wav, mimeType: 'audio/wav'));
      clock.start();
      _levelTimer = Timer.periodic(const Duration(milliseconds: 40), (_) {
        final i = clock.elapsedMilliseconds ~/ 50;
        speakingLevel.value = i < envelope.length ? envelope[i] : 0;
      });
      final limit = Duration(milliseconds: envelope.length * 50 + 4000);
      await done.future.timeout(limit, onTimeout: () {});
    } finally {
      await sub.cancel();
      _levelTimer?.cancel();
      speakingLevel.value = 0;
      isSpeaking.value = false;
      if (identical(_speaking, done)) _speaking = null;
    }
  }

  Future<void> stopSpeaking() async {
    final speaking = _speaking;
    if (speaking == null) return;
    await _player.stop();
    if (!speaking.isCompleted) speaking.complete();
  }

  Future<void> chime() async {
    try {
      await _chimePlayer.stop();
      await _chimePlayer.play(BytesSource(_chime, mimeType: 'audio/wav'));
    } catch (_) {}
  }

  Future<void> dispose() async {
    _levelTimer?.cancel();
    await stopMic();
    await _recorder.dispose();
    await _player.dispose();
    await _chimePlayer.dispose();
  }
}
