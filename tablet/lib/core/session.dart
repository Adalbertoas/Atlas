import 'dart:async';

import 'package:flutter/foundation.dart';

import 'api.dart';
import 'config.dart';
import 'files.dart';
import 'hands_free.dart';
import 'models.dart';
import 'voice.dart';

/// Estado visual del núcleo de partículas (los mismos estados que el escritorio).
enum CoreMode { idle, listening, thinking, speaking, error }

/// Todo lo que vive mientras la tablet está conectada a un backend.
class Session {
  Session(this.prefs, this.config)
      : api = AtlasApi(config),
        voice = VoiceService() {
    files = GeneratedFiles(api);
    chat = ChatController(this);
    engine = VoiceEngine(api: api, voice: voice, prefs: prefs, onCommand: (text) => chat.send(text, spoken: true));
    core = Listenable.merge([chat, engine, voice.isSpeaking]);
  }

  final AppPrefs prefs;
  final ServerConfig config;
  final AtlasApi api;
  final VoiceService voice;
  late final GeneratedFiles files;
  late final ChatController chat;
  late final VoiceEngine engine;

  /// Avisa cuando cambia algo que mueve el núcleo.
  late final Listenable core;

  /// Nombre del asistente y cómo llama al usuario (Configuración → Personalidad).
  final assistantName = ValueNotifier<String>('ATLAS');
  final userName = ValueNotifier<String>('');

  CoreMode get coreMode {
    if (voice.isSpeaking.value) return CoreMode.speaking;
    if (chat.busy || engine.phase == ListenPhase.busy) return CoreMode.thinking;
    if (engine.phase == ListenPhase.command) return CoreMode.listening;
    if (chat.lastFailed) return CoreMode.error;
    return CoreMode.idle;
  }

  /// Nivel que anima el núcleo: la voz de ATLAS al hablar, el micrófono al escuchar.
  double get coreLevel => voice.isSpeaking.value ? voice.speakingLevel.value : engine.level.value;

  String get statusLabel => switch (coreMode) {
        CoreMode.speaking => 'Hablando',
        CoreMode.thinking => 'Pensando',
        CoreMode.listening => engine.hearing ? 'Te escucho' : 'Escuchando',
        CoreMode.error => 'Sin conexión',
        CoreMode.idle => engine.phase == ListenPhase.standby ? 'Di "Atlas"' : 'En espera',
      };

  Future<void> start() async {
    unawaited(loadPersonality());
    if (prefs.handsFree) await engine.setHandsFree(true);
  }

  Future<void> loadPersonality() async {
    try {
      final p = await api.personality();
      final name = (p['assistant_name'] as String? ?? '').trim();
      assistantName.value = name.isEmpty ? 'ATLAS' : name;
      userName.value = (p['user_name'] as String? ?? '').trim();
    } catch (_) {
      // Sin personalidad se usa "ATLAS": no vale la pena interrumpir al usuario.
    }
  }

  /// Lee un texto con la voz de ATLAS y espera a que termine. El micrófono de
  /// manos libres se ignora mientras tanto para que no se escuche a sí mismo.
  Future<void> speak(String text) async {
    final plain = text
        .replaceAll(RegExp(r'\[([^\]]+)\]\([^)]+\)'), r'$1') // enlaces markdown
        .replaceAll(RegExp(r'[*_`#>|]'), '')
        .replaceAll(RegExp(r'\n{2,}'), '\n')
        .trim();
    if (plain.isEmpty) return;
    engine.suspend();
    try {
      await voice.speak(await api.speak(plain));
    } catch (_) {
      // Si la voz falla, la respuesta igual está en pantalla.
    } finally {
      engine.resume();
    }
  }

  void dispose() {
    engine.dispose();
    chat.dispose();
    voice.dispose();
    api.close();
  }
}

/// Estado del chat: mensajes, adjuntos pendientes y respuestas habladas.
class ChatController extends ChangeNotifier {
  ChatController(this._session);

  final Session _session;
  final messages = <ChatMessage>[];
  final pending = <ChatAttachment>[];
  String? _conversationId;
  bool busy = false;
  bool lastFailed = false;

  /// Texto para dejar en el cuadro del chat (pedidos que el usuario completa).
  final draft = ValueNotifier<String?>(null);

  /// Pedido pendiente de abrir la cámara (acción "Factura a Excel"); el chat
  /// lo atiende apenas se muestra.
  final cameraRequested = ValueNotifier<bool>(false);

  static const maxAttachments = 6;

  bool get speakReplies => _session.prefs.speakReplies;
  set speakReplies(bool value) {
    _session.prefs.speakReplies = value;
    if (!value) _session.voice.stopSpeaking();
    notifyListeners();
  }

  /// Devuelve false si ya no entran más archivos.
  bool addAttachment(ChatAttachment attachment) {
    if (pending.length >= maxAttachments) return false;
    pending.add(attachment);
    notifyListeners();
    return true;
  }

  void removeAttachment(ChatAttachment attachment) {
    pending.remove(attachment);
    notifyListeners();
  }

  void newChat() {
    messages.clear();
    pending.clear();
    _conversationId = null;
    lastFailed = false;
    _session.voice.stopSpeaking();
    notifyListeners();
  }

  /// Envía el mensaje y, si corresponde, lee la respuesta en voz alta.
  /// Termina cuando ATLAS terminó de hablar (lo usa la conversación por voz).
  Future<void> send(String text, {bool spoken = false}) async {
    final message = text.trim();
    final files = List<ChatAttachment>.of(pending);
    if ((message.isEmpty && files.isEmpty) || busy) return;
    messages.add(ChatMessage.user(message, attachments: files, spoken: spoken));
    pending.clear();
    busy = true;
    notifyListeners();
    ChatReply? reply;
    try {
      reply = await _session.api.chat(message, conversationId: _conversationId, attachments: files);
      _conversationId = reply.conversationId ?? _conversationId;
      messages.add(ChatMessage.assistant(reply));
      lastFailed = false;
    } catch (error) {
      messages.add(ChatMessage.error('$error'));
      lastFailed = true;
    } finally {
      busy = false;
      notifyListeners();
    }
    if (reply != null && reply.text.isNotEmpty && (spoken || speakReplies)) await _session.speak(reply.text);
  }

  Future<void> answerConfirmation(ChatMessage message, bool approve) async {
    final id = message.confirmationId;
    if (id == null) return;
    message.confirmationId = null;
    if (message.text.isEmpty) message.text = approve ? 'Acción confirmada.' : 'Acción cancelada.';
    busy = true;
    notifyListeners();
    ChatReply? reply;
    try {
      reply = await _session.api.confirm(id, approve);
      if (reply.text.isNotEmpty || reply.files.isNotEmpty) messages.add(ChatMessage.assistant(reply));
    } catch (error) {
      messages.add(ChatMessage.error('$error'));
    } finally {
      busy = false;
      notifyListeners();
    }
    if (reply != null && reply.text.isNotEmpty && speakReplies) await _session.speak(reply.text);
  }

  /// El último mensaje de ATLAS (para el subtítulo de la vista del núcleo).
  ChatMessage? get lastReply {
    for (final m in messages.reversed) {
      if (!m.fromUser) return m;
    }
    return null;
  }
}
