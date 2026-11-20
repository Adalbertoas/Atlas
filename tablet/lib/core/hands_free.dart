import 'dart:async';
import 'dart:collection';
import 'dart:typed_data';

import 'package:flutter/foundation.dart';
import 'package:wakelock_plus/wakelock_plus.dart';

import 'api.dart';
import 'config.dart';
import 'segmenter.dart';
import 'voice.dart';
import 'wake_word.dart';
import 'wav.dart';

enum ListenPhase {
  /// Micrófono cerrado.
  off,

  /// Manos libres: esperando oír "Atlas".
  standby,

  /// Escuchando un pedido (después de "Atlas", del botón o de una respuesta).
  command,

  /// ATLAS está resolviendo un pedido o hablando: el micrófono se ignora
  /// para que no se escuche a sí mismo.
  busy,
}

/// Conversación por voz, como "Escuchar «Atlas»" en el escritorio:
///  - en reposo cada frase se transcribe y solo actúa si empieza por "Atlas";
///  - "Atlas" solo → suena el aviso y el siguiente pedido no necesita el nombre;
///  - después de cada respuesta hay unos segundos para seguir sin repetir "Atlas".
class VoiceEngine extends ChangeNotifier {
  VoiceEngine({required AtlasApi api, required VoiceService voice, required AppPrefs prefs, required this.onCommand})
      : _api = api,
        _voice = voice,
        _prefs = prefs {
    _segmenter
      ..onUtterance = _onUtterance
      ..onSpeechStart = () {
        hearing = true;
        notifyListeners();
      };
    _applyPrefs();
  }

  final AtlasApi _api;
  final VoiceService _voice;
  final AppPrefs _prefs;

  /// Manda el pedido a ATLAS y espera hasta que terminó de responder (y de hablar).
  final Future<void> Function(String command) onCommand;

  final _segmenter = SpeechSegmenter();
  final _queue = Queue<Int16List>();
  bool _processing = false;
  Timer? _awaitTimer;
  int _suspended = 0;

  ListenPhase phase = ListenPhase.off;
  bool handsFree = false;

  /// Hay voz en curso (para el indicador "te escucho").
  bool hearing = false;

  /// Lo último que se entendió, para mostrarlo en pantalla.
  String heard = '';

  /// Nivel del micrófono (0..1), para el medidor y el núcleo.
  final level = ValueNotifier<double>(0);

  static const _awaitMs = {'manual': 8000, 'wake': 6000, 'follow-up': 5000};

  double get noiseFloorDb => _segmenter.noiseFloorDb;
  double get thresholdDb => _segmenter.thresholdDb;
  double get levelDb => _segmenter.levelDb;

  void _applyPrefs() => _segmenter.sensitivity = _prefs.micSensitivity;

  set sensitivity(double value) {
    _prefs.micSensitivity = value;
    _applyPrefs();
    notifyListeners();
  }

  /// Cambió una preferencia que se muestra en pantalla.
  void refresh() => notifyListeners();

  // --- Encender / apagar ---------------------------------------------------------

  /// Devuelve un aviso para el usuario si no se pudo.
  Future<String?> setHandsFree(bool on) async {
    if (on == handsFree) return null;
    if (on) {
      if (!await _startMic()) return 'Dale permiso de micrófono a ATLAS en los ajustes de Android.';
      handsFree = true;
      _prefs.handsFree = true;
      if (phase == ListenPhase.off) _setPhase(ListenPhase.standby);
      // Como estación de voz, la pantalla no se apaga mientras escucha.
      unawaited(WakelockPlus.enable());
    } else {
      handsFree = false;
      _prefs.handsFree = false;
      unawaited(WakelockPlus.disable());
      if (phase != ListenPhase.busy) await _stopListening();
    }
    notifyListeners();
    return null;
  }

  /// Botón del micrófono: escuchar un pedido sin decir "Atlas". Si ya estaba
  /// escuchando un pedido, lo envía en ese momento.
  Future<String?> listenOnce() async {
    if (phase == ListenPhase.command) {
      if (!_segmenter.flush()) await cancelCommand();
      return null;
    }
    if (phase == ListenPhase.busy) return null;
    if (!await _startMic()) return 'Dale permiso de micrófono a ATLAS en los ajustes de Android.';
    _enterCommand('manual', chime: false);
    return null;
  }

  Future<void> cancelCommand() async {
    _awaitTimer?.cancel();
    _segmenter.reset();
    hearing = false;
    if (handsFree) {
      _setPhase(ListenPhase.standby);
    } else {
      await _stopListening();
    }
  }

  Future<bool> _startMic() async {
    if (_voice.micOn) return true;
    _segmenter.reset();
    return _voice.startMic(_onAudio, onError: (_) => _restartSoon());
  }

  Future<void> _stopListening() async {
    _awaitTimer?.cancel();
    _queue.clear();
    hearing = false;
    level.value = 0;
    await _voice.stopMic();
    _setPhase(ListenPhase.off);
  }

  /// El micrófono se cortó (otra app lo tomó un momento): reintentar.
  void _restartSoon() {
    Timer(const Duration(seconds: 2), () async {
      if (!handsFree) return;
      await _voice.stopMic();
      await _startMic();
    });
  }

  /// La app pasó a segundo plano: Android no deja usar el micrófono ahí.
  Future<void> pauseForBackground() async {
    if (_voice.micOn) await _voice.stopMic();
  }

  Future<void> resumeFromBackground() async {
    if (handsFree && !_voice.micOn) {
      await _startMic();
      if (phase == ListenPhase.off) _setPhase(ListenPhase.standby);
    }
  }

  /// Mientras ATLAS habla por otro motivo (respuesta a un mensaje escrito), el
  /// micrófono se ignora para que no se escuche a sí mismo.
  void suspend() {
    _suspended++;
    _segmenter.reset();
  }

  void resume() {
    if (_suspended > 0) _suspended--;
    if (_suspended == 0) _segmenter.reset();
  }

  // --- Audio --------------------------------------------------------------------

  void _onAudio(Uint8List bytes) {
    if (phase == ListenPhase.off || phase == ListenPhase.busy || _suspended > 0) {
      level.value = 0;
      return;
    }
    _segmenter.endSilenceMs = phase == ListenPhase.command ? 800 : 550;
    _segmenter.add(bytes);
    level.value = ((_segmenter.levelDb + 70) / 50).clamp(0, 1).toDouble();
  }

  void _onUtterance(Int16List samples, int voicedMs) {
    hearing = false;
    notifyListeners();
    if (voicedMs < 200) return; // un golpe, una tos
    _queue.add(samples);
    if (!_processing) unawaited(_drain());
  }

  /// Las frases se transcriben en orden. Si mientras se transcribía "Atlas"
  /// el usuario ya dijo el pedido, esa segunda frase se toma como pedido.
  Future<void> _drain() async {
    _processing = true;
    try {
      while (_queue.isNotEmpty && phase != ListenPhase.busy && phase != ListenPhase.off) {
        final samples = _queue.removeFirst();
        final inCommand = phase == ListenPhase.command;
        String text;
        try {
          text = cleanTranscript(await _api.transcribe(wavFromPcm16(samples), prompt: inCommand ? null : wakePrompt));
        } catch (_) {
          continue; // sin conexión: no interrumpir la escucha por una frase
        }
        if (text.isEmpty) continue;
        final wake = detectWakeWord(text);
        if (inCommand || phase == ListenPhase.command) {
          final command = wake.detected ? wake.command : text;
          if (command.isEmpty) {
            _enterCommand('wake'); // volvió a decir solo "Atlas"
          } else {
            await _execute(command);
          }
        } else if (wake.detected) {
          if (wake.command.isEmpty) {
            _enterCommand('wake');
          } else {
            await _execute(wake.command);
          }
        }
      }
    } finally {
      _processing = false;
    }
  }

  void _enterCommand(String reason, {bool chime = true}) {
    _awaitTimer?.cancel();
    if (chime && _prefs.wakeSound) unawaited(_voice.chime());
    _setPhase(ListenPhase.command);
    _awaitTimer = Timer(Duration(milliseconds: _awaitMs[reason]!), () {
      // Nadie habló: si estaba a mitad de una frase, se la deja terminar.
      if (phase == ListenPhase.command && !_segmenter.inSpeech) unawaited(cancelCommand());
    });
  }

  Future<void> _execute(String command) async {
    _awaitTimer?.cancel();
    _queue.clear();
    heard = command;
    _setPhase(ListenPhase.busy);
    var completed = false;
    try {
      await onCommand(command);
      completed = true;
    } finally {
      // Un respiro para que el final del audio no entre como frase.
      await Future<void>.delayed(const Duration(milliseconds: 250));
      _segmenter.reset();
      if (handsFree) {
        if (completed && _prefs.followUp) {
          _enterCommand('follow-up', chime: false);
        } else {
          _setPhase(ListenPhase.standby);
        }
      } else {
        await _stopListening();
      }
    }
  }

  void _setPhase(ListenPhase next) {
    phase = next;
    if (next != ListenPhase.command) hearing = false;
    notifyListeners();
  }

  @override
  void dispose() {
    _awaitTimer?.cancel();
    unawaited(WakelockPlus.disable());
    level.dispose();
    super.dispose();
  }
}
