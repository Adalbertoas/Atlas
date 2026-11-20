import 'package:file_picker/file_picker.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:image_picker/image_picker.dart';

import '../core/hands_free.dart';
import '../core/models.dart';
import '../core/session.dart';
import '../ui/hud_art.dart';
import '../ui/markdown.dart';
import '../ui/theme.dart';
import 'voice_controls.dart';

/// Panel "Chat con ATLAS" con el aspecto del escritorio (jarvis.css).
class ChatView extends StatefulWidget {
  const ChatView({super.key, required this.session, required this.onOpenCore});

  final Session session;
  final VoidCallback onOpenCore;

  @override
  State<ChatView> createState() => _ChatViewState();
}

class _ChatViewState extends State<ChatView> {
  final _input = TextEditingController();
  final _focus = FocusNode();
  final _scroll = ScrollController();
  final _picker = ImagePicker();
  int _seen = 0;

  Session get _session => widget.session;
  ChatController get _chat => _session.chat;

  @override
  void initState() {
    super.initState();
    _chat.addListener(_onChat);
    _chat.draft.addListener(_onDraft);
    _chat.cameraRequested.addListener(_onCameraRequest);
    WidgetsBinding.instance.addPostFrameCallback((_) {
      _onDraft();
      _onCameraRequest();
    });
  }

  @override
  void dispose() {
    _chat.removeListener(_onChat);
    _chat.draft.removeListener(_onDraft);
    _chat.cameraRequested.removeListener(_onCameraRequest);
    _input.dispose();
    _focus.dispose();
    _scroll.dispose();
    super.dispose();
  }

  void _onChat() {
    if (_chat.messages.length == _seen && !_chat.busy) return;
    _seen = _chat.messages.length;
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (_scroll.hasClients) {
        _scroll.animateTo(_scroll.position.maxScrollExtent, duration: const Duration(milliseconds: 250), curve: Curves.easeOut);
      }
    });
  }

  void _onDraft() {
    final draft = _chat.draft.value;
    if (draft == null) return;
    _chat.draft.value = null;
    _input
      ..text = draft
      ..selection = TextSelection.collapsed(offset: draft.length);
    _focus.requestFocus();
  }

  void _onCameraRequest() {
    if (!_chat.cameraRequested.value) return;
    _chat.cameraRequested.value = false;
    _attach('camera');
  }

  void _send() {
    final text = _input.text;
    if (text.trim().isEmpty && _chat.pending.isEmpty) return;
    _input.clear();
    _chat.send(text);
  }

  // --- Adjuntos -------------------------------------------------------------------

  static String _mimeFor(String name) => switch (name.toLowerCase().split('.').last) {
        'png' => 'image/png',
        'webp' => 'image/webp',
        'gif' => 'image/gif',
        'pdf' => 'application/pdf',
        _ => 'image/jpeg',
      };

  Future<void> _addPicked(Iterable<XFile> files) async {
    var refused = 0;
    for (final file in files) {
      final bytes = await file.readAsBytes();
      if (!_chat.addAttachment(ChatAttachment(name: file.name, mimeType: _mimeFor(file.name), bytes: bytes))) refused++;
    }
    if (refused > 0 && mounted) showMessage(context, 'Máximo ${ChatController.maxAttachments} archivos por mensaje.');
  }

  Future<void> _attach(String source) async {
    final room = ChatController.maxAttachments - _chat.pending.length;
    if (room <= 0) {
      showMessage(context, 'Máximo ${ChatController.maxAttachments} archivos por mensaje.');
      return;
    }
    try {
      switch (source) {
        case 'camera':
          // 2600 px alcanza para la letra chica de un ticket y no sube 12 MP.
          final photo = await _picker.pickImage(source: ImageSource.camera, maxWidth: 2600, maxHeight: 2600, imageQuality: 88);
          if (photo != null) await _addPicked([photo]);
        case 'gallery':
          final photos = await _picker.pickMultiImage(maxWidth: 2600, maxHeight: 2600, imageQuality: 88, limit: room > 1 ? room : null);
          await _addPicked(photos.take(room));
        case 'file':
          final picked = await FilePicker.pickFiles(type: FileType.custom, allowedExtensions: const ['pdf', 'jpg', 'jpeg', 'png', 'webp', 'gif']);
          await _addPicked([for (final f in picked.take(room)) f.xFile]);
      }
    } on PlatformException catch (error) {
      if (mounted) showMessage(context, 'No pude acceder: ${error.message ?? error.code}');
    }
  }

  void _showAttachMenu() {
    showModalBottomSheet<void>(
      context: context,
      showDragHandle: true,
      builder: (context) => SafeArea(
        child: Column(mainAxisSize: MainAxisSize.min, children: [
          for (final (id, icon, title, subtitle) in [
            ('camera', Icons.photo_camera_outlined, 'Tomar una foto', 'Ideal para facturas y recibos'),
            ('gallery', Icons.photo_library_outlined, 'Elegir de la galería', null),
            ('file', Icons.picture_as_pdf_outlined, 'PDF o archivo', null),
          ])
            ListTile(
              leading: Icon(icon, color: Hud.cyan),
              title: Text(title),
              subtitle: subtitle == null ? null : Text(subtitle, style: const TextStyle(color: Hud.muted)),
              onTap: () {
                Navigator.pop(context);
                _attach(id);
              },
            ),
          const SizedBox(height: 8),
        ]),
      ),
    );
  }

  // --- Vista ----------------------------------------------------------------------

  @override
  Widget build(BuildContext context) {
    return ListenableBuilder(
      listenable: Listenable.merge([_chat, _session.core]),
      builder: (context, _) => ValueListenableBuilder(
        valueListenable: _session.assistantName,
        builder: (context, name, _) => HudPanel(
          title: 'Chat con $name',
          icon: Icons.auto_awesome,
          active: true,
          padding: EdgeInsets.zero,
          child: Column(children: [
            _statusRow(name),
            Expanded(child: _chat.messages.isEmpty ? _welcome(name) : _messageList(name)),
            if (_session.engine.phase == ListenPhase.command) _liveListening(),
            if (_chat.pending.isNotEmpty) _tray(),
            _composer(),
          ]),
        ),
      ),
    );
  }

  /// "ATLAS EN ESPERA" con el mini núcleo, como .voice-status del escritorio.
  Widget _statusRow(String name) {
    final label = switch (_session.coreMode) {
      CoreMode.speaking => '$name está respondiendo',
      CoreMode.thinking => '$name está pensando',
      CoreMode.listening => '$name te escucha',
      CoreMode.error => '$name sin conexión',
      CoreMode.idle => _session.engine.phase == ListenPhase.standby ? '$name espera "Atlas"' : '$name en espera',
    };
    return Padding(
      padding: const EdgeInsets.fromLTRB(14, 8, 10, 4),
      child: Row(children: [
        GestureDetector(onTap: widget.onOpenCore, child: NeuralCore(session: _session, size: 30, particles: 90, showRings: false)),
        const SizedBox(width: 8),
        Expanded(child: Text(label.toUpperCase(), maxLines: 1, overflow: TextOverflow.ellipsis, style: Hud.label())),
        IconButton(
          tooltip: _chat.speakReplies ? 'Respuestas habladas: sí' : 'Respuestas habladas: no',
          visualDensity: VisualDensity.compact,
          icon: Icon(_chat.speakReplies ? Icons.volume_up : Icons.volume_off_outlined, color: _chat.speakReplies ? Hud.cyan : Hud.dim, size: 19),
          onPressed: () => _chat.speakReplies = !_chat.speakReplies,
        ),
        if (_session.voice.isSpeaking.value)
          IconButton(
            tooltip: 'Callar',
            visualDensity: VisualDensity.compact,
            icon: const Icon(Icons.stop_circle_outlined, color: Hud.amber, size: 19),
            onPressed: _session.voice.stopSpeaking,
          ),
        if (_chat.messages.isNotEmpty) ...[
          const SizedBox(width: 4),
          OutlinedButton.icon(
            style: OutlinedButton.styleFrom(
              visualDensity: VisualDensity.compact,
              foregroundColor: Hud.cyan,
              textStyle: Hud.label(size: 9.5, color: Hud.cyan),
              padding: const EdgeInsets.symmetric(horizontal: 10),
            ),
            onPressed: _chat.busy ? null : _chat.newChat,
            icon: const Icon(Icons.add, size: 14),
            label: const Text('NUEVO CHAT'),
          ),
        ],
      ]),
    );
  }

  Widget _welcome(String name) {
    final user = _session.userName.value;
    final hour = DateTime.now().hour;
    final greeting = hour < 12 ? 'Buenos días' : (hour < 19 ? 'Buenas tardes' : 'Buenas noches');
    final starters = [
      (Icons.receipt_long_outlined, 'Factura a Excel', ''),
      (Icons.wb_sunny_outlined, '¿Qué clima hace?', '¿Cómo está el clima hoy?'),
      (Icons.public, 'Noticias de hoy', '¿Cuáles son las noticias más importantes de hoy?'),
      (Icons.auto_awesome_outlined, 'Resumen del día', 'Dame mi resumen del día'),
      (Icons.notifications_none, 'Recordarme algo', 'Recuérdame '),
      (Icons.image_outlined, 'Crear una imagen', 'Crea una imagen de '),
    ];
    return LayoutBuilder(builder: (context, constraints) {
      final coreSize = (constraints.maxHeight * .34).clamp(70.0, 130.0);
      return SingleChildScrollView(
        padding: const EdgeInsets.fromLTRB(20, 8, 20, 16),
        child: ConstrainedBox(
          constraints: BoxConstraints(minHeight: constraints.maxHeight - 24),
          child: Column(mainAxisAlignment: MainAxisAlignment.center, children: [
            Row(children: [
              GestureDetector(onTap: widget.onOpenCore, child: NeuralCore(session: _session, size: coreSize, particles: 320)),
              const SizedBox(width: 16),
              Expanded(
                child: Container(
                  padding: const EdgeInsets.fromLTRB(18, 14, 18, 14),
                  decoration: const BoxDecoration(
                    border: Border(left: BorderSide(color: Hud.cyan, width: 2), top: BorderSide(color: Hud.line), right: BorderSide(color: Hud.line), bottom: BorderSide(color: Hud.line)),
                    borderRadius: BorderRadius.only(topRight: Radius.circular(8), bottomRight: Radius.circular(8)),
                    gradient: LinearGradient(colors: [Color(0x143FE6FF), Color(0x6603101C)]),
                  ),
                  child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                    Text('$greeting${user.isEmpty ? '' : ', $user'}. Soy $name.',
                        style: const TextStyle(fontFamily: Hud.display, fontSize: 21, fontWeight: FontWeight.w600, color: Color(0xFFEFFCFF), height: 1.2)),
                    const SizedBox(height: 4),
                    const Text('¿En qué te ayudo?', style: TextStyle(fontSize: 15.5)),
                    const SizedBox(height: 10),
                    Text(
                      _session.engine.handsFree ? 'En línea · di "Atlas" y tu pedido, o toca el micrófono.' : 'En línea · puedo usar tus herramientas, tu memoria y la web.',
                      style: Hud.label(size: 10, color: Hud.amber, spacing: .03),
                    ),
                  ]),
                ),
              ),
            ]),
            const SizedBox(height: 22),
            Wrap(spacing: 8, runSpacing: 8, alignment: WrapAlignment.center, children: [
              for (final (icon, label, prompt) in starters)
                _QuickButton(
                  icon: icon,
                  label: label,
                  onTap: () {
                    if (label == 'Factura a Excel') {
                      _input.text = 'Pásalo a Excel';
                      _attach('camera');
                    } else if (prompt.endsWith(' ')) {
                      _chat.draft.value = prompt;
                    } else {
                      _chat.send(prompt);
                    }
                  },
                ),
            ]),
          ]),
        ),
      );
    });
  }

  Widget _messageList(String name) {
    return ListView.builder(
      controller: _scroll,
      padding: const EdgeInsets.fromLTRB(18, 10, 18, 8),
      itemCount: _chat.messages.length + (_chat.busy ? 1 : 0),
      itemBuilder: (context, index) {
        if (index == _chat.messages.length) return const _Typing();
        final message = _chat.messages[index];
        return message.fromUser
            ? _UserBubble(message: message, onZoom: _zoom)
            : _AssistantBubble(
                message: message,
                name: name,
                session: _session,
                onZoom: _zoom,
                onAnswer: (approve) => _chat.answerConfirmation(message, approve),
              );
      },
    );
  }

  void _zoom(MemoryImage image) {
    showDialog<void>(
      context: context,
      builder: (context) => Dialog.fullscreen(
        backgroundColor: Colors.black,
        child: Stack(children: [
          Positioned.fill(child: InteractiveViewer(maxScale: 6, child: Center(child: Image(image: image)))),
          Positioned(top: 12, right: 12, child: IconButton.filled(onPressed: () => Navigator.pop(context), icon: const Icon(Icons.close))),
        ]),
      ),
    );
  }

  /// Transcripción en vivo del escritorio (.live-transcript), con el nivel del micrófono.
  Widget _liveListening() {
    final engine = _session.engine;
    return Container(
      margin: const EdgeInsets.fromLTRB(14, 0, 14, 8),
      padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 10),
      decoration: BoxDecoration(
        color: const Color(0x2E3DF0A6),
        border: Border.all(color: const Color(0x803DF0A6)),
        borderRadius: BorderRadius.circular(3),
      ),
      child: Row(children: [
        ValueListenableBuilder(
          valueListenable: engine.level,
          builder: (_, level, _) => Container(
            width: 10 + level * 8,
            height: 10 + level * 8,
            decoration: BoxDecoration(color: Hud.green, shape: BoxShape.circle, boxShadow: [BoxShadow(color: Hud.green, blurRadius: 6 + level * 10)]),
          ),
        ),
        const SizedBox(width: 12),
        Expanded(child: Text(engine.hearing ? 'Te escucho…' : 'Di tu pedido… (se envía solo al callarte)', style: const TextStyle(fontSize: 14))),
        TextButton(onPressed: engine.cancelCommand, child: const Text('CANCELAR')),
      ]),
    );
  }

  Widget _tray() {
    return Container(
      height: 92,
      decoration: const BoxDecoration(border: Border(top: BorderSide(color: Hud.line))),
      child: ListView(
        scrollDirection: Axis.horizontal,
        padding: const EdgeInsets.fromLTRB(14, 10, 14, 6),
        children: [
          for (final attachment in _chat.pending)
            Padding(
              padding: const EdgeInsets.only(right: 8),
              child: Stack(clipBehavior: Clip.none, children: [
                _Thumb(attachment: attachment, size: 72),
                Positioned(
                  top: -6,
                  right: -6,
                  child: InkWell(
                    onTap: () => _chat.removeAttachment(attachment),
                    child: const CircleAvatar(radius: 11, backgroundColor: Hud.red, child: Icon(Icons.close, size: 14, color: Colors.white)),
                  ),
                ),
              ]),
            ),
        ],
      ),
    );
  }

  Widget _composer() {
    final listening = _session.engine.phase == ListenPhase.command;
    return Container(
      padding: const EdgeInsets.fromLTRB(12, 12, 14, 12),
      decoration: const BoxDecoration(
        border: Border(top: BorderSide(color: Hud.line)),
        gradient: LinearGradient(begin: Alignment.bottomCenter, end: Alignment.topCenter, colors: [Color(0x0A3FE6FF), Colors.transparent]),
      ),
      child: Row(crossAxisAlignment: CrossAxisAlignment.center, children: [
        IconButton(
          tooltip: 'Adjuntar foto o PDF',
          onPressed: _chat.busy ? null : _showAttachMenu,
          icon: const Icon(Icons.link),
          color: Hud.muted,
        ),
        Expanded(
          child: TextField(
            controller: _input,
            focusNode: _focus,
            minLines: 1,
            maxLines: 4,
            textCapitalization: TextCapitalization.sentences,
            style: const TextStyle(fontSize: 14),
            decoration: InputDecoration(
              hintText: _chat.pending.isNotEmpty ? '¿Qué hago con esto? (ej. pásalo a Excel)' : 'Escribe tu mensaje...',
              isDense: true,
            ),
          ),
        ),
        const SizedBox(width: 8),
        Material(
          color: listening ? const Color(0xBFFF5D6C) : Colors.transparent,
          shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(3)),
          child: IconButton(
            tooltip: listening ? 'Enviar ya (también se envía solo al callarte)' : 'Hablar con ATLAS (se envía solo al callarte)',
            onPressed: _chat.busy ? null : () => listenOnce(context, _session),
            icon: Icon(listening ? Icons.stop : Icons.mic_none, color: listening ? Colors.white : Hud.muted),
          ),
        ),
        const SizedBox(width: 8),
        _SendButton(onTap: _chat.busy ? null : _send),
      ]),
    );
  }
}

class _QuickButton extends StatelessWidget {
  const _QuickButton({required this.icon, required this.label, required this.onTap});

  final IconData icon;
  final String label;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    return Material(
      color: const Color(0x99031220),
      shape: RoundedRectangleBorder(side: const BorderSide(color: Hud.line), borderRadius: BorderRadius.circular(3)),
      child: InkWell(
        onTap: onTap,
        borderRadius: BorderRadius.circular(3),
        child: Padding(
          padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 10),
          child: Row(mainAxisSize: MainAxisSize.min, children: [
            Icon(icon, size: 16, color: Hud.cyan),
            const SizedBox(width: 8),
            Text(label, style: const TextStyle(fontSize: 13)),
          ]),
        ),
      ),
    );
  }
}

/// Botón de enviar redondo con brillo cian (.composer .send).
class _SendButton extends StatelessWidget {
  const _SendButton({required this.onTap});

  final VoidCallback? onTap;

  @override
  Widget build(BuildContext context) {
    final enabled = onTap != null;
    return GestureDetector(
      onTap: onTap,
      child: Container(
        width: 46,
        height: 46,
        decoration: BoxDecoration(
          shape: BoxShape.circle,
          border: Border.all(color: enabled ? Hud.cyan : Hud.dim),
          gradient: const RadialGradient(colors: [Color(0x733FE6FF), Color(0x590A7FA6), Color(0xE6021422)], stops: [0, .6, 1]),
          boxShadow: enabled ? const [BoxShadow(color: Color(0x733FE6FF), blurRadius: 16)] : null,
        ),
        child: Icon(Icons.send, color: enabled ? Colors.white : Hud.dim, size: 20),
      ),
    );
  }
}

class _Thumb extends StatelessWidget {
  const _Thumb({required this.attachment, required this.size, this.onTap});

  final ChatAttachment attachment;
  final double size;
  final VoidCallback? onTap;

  @override
  Widget build(BuildContext context) {
    final child = attachment.isImage
        ? Image.memory(attachment.bytes, width: size, height: size, fit: BoxFit.cover, cacheWidth: (size * 3).round())
        : Container(
            width: size,
            height: size,
            color: const Color(0x24FF5D6C),
            alignment: Alignment.center,
            child: Column(mainAxisSize: MainAxisSize.min, children: [
              const Icon(Icons.picture_as_pdf, color: Hud.red),
              Padding(
                padding: const EdgeInsets.symmetric(horizontal: 4),
                child: Text(attachment.name, maxLines: 1, overflow: TextOverflow.ellipsis, style: const TextStyle(fontSize: 9)),
              ),
            ]),
          );
    return InkWell(
      onTap: onTap,
      child: Container(
        decoration: BoxDecoration(border: Border.all(color: Hud.line2), borderRadius: BorderRadius.circular(3)),
        clipBehavior: Clip.antiAlias,
        child: child,
      ),
    );
  }
}

/// Burbuja del usuario: borde ámbar a la derecha (.user-message).
class _UserBubble extends StatelessWidget {
  const _UserBubble({required this.message, required this.onZoom});

  final ChatMessage message;
  final ValueChanged<MemoryImage> onZoom;

  @override
  Widget build(BuildContext context) {
    return Align(
      alignment: Alignment.centerRight,
      child: FractionallySizedBox(
        widthFactor: .84,
        alignment: Alignment.centerRight,
        child: Align(
          alignment: Alignment.centerRight,
          child: Container(
            margin: const EdgeInsets.only(bottom: 12),
            padding: const EdgeInsets.fromLTRB(14, 9, 14, 10),
            decoration: const BoxDecoration(
              border: Border(right: BorderSide(color: Hud.amber, width: 2), top: BorderSide(color: Color(0x38FFB547)), left: BorderSide(color: Color(0x38FFB547)), bottom: BorderSide(color: Color(0x38FFB547))),
              borderRadius: BorderRadius.only(topLeft: Radius.circular(8), bottomLeft: Radius.circular(8)),
              gradient: LinearGradient(begin: Alignment.centerRight, end: Alignment.centerLeft, colors: [Color(0x14FFB547), Color(0x7303101C)]),
            ),
            child: Column(crossAxisAlignment: CrossAxisAlignment.end, mainAxisSize: MainAxisSize.min, children: [
              Row(mainAxisSize: MainAxisSize.min, children: [
                if (message.spoken) ...[const Icon(Icons.mic, size: 11, color: Hud.amber), const SizedBox(width: 4)],
                Text('TÚ', style: Hud.label(size: 9.5, color: Hud.amber, spacing: .14)),
              ]),
              const SizedBox(height: 5),
              if (message.attachments.isNotEmpty)
                Wrap(spacing: 6, runSpacing: 6, alignment: WrapAlignment.end, children: [
                  for (final a in message.attachments) _Thumb(attachment: a, size: 110, onTap: a.isImage ? () => onZoom(MemoryImage(a.bytes)) : null),
                ]),
              if (message.attachments.isNotEmpty && message.text.isNotEmpty) const SizedBox(height: 8),
              if (message.text.isNotEmpty) Text(message.text, style: const TextStyle(fontSize: 14, height: 1.45)),
            ]),
          ),
        ),
      ),
    );
  }
}

/// Burbuja de ATLAS: borde cian a la izquierda (.atlas-message).
class _AssistantBubble extends StatelessWidget {
  const _AssistantBubble({required this.message, required this.name, required this.session, required this.onZoom, required this.onAnswer});

  final ChatMessage message;
  final String name;
  final Session session;
  final ValueChanged<MemoryImage> onZoom;
  final ValueChanged<bool> onAnswer;

  @override
  Widget build(BuildContext context) {
    final error = message.isError;
    final accent = error ? Hud.red : Hud.cyan;
    return Align(
      alignment: Alignment.centerLeft,
      child: FractionallySizedBox(
        widthFactor: .9,
        alignment: Alignment.centerLeft,
        child: Align(
          alignment: Alignment.centerLeft,
          child: Container(
            margin: const EdgeInsets.only(bottom: 12),
            padding: const EdgeInsets.fromLTRB(14, 9, 14, 6),
            decoration: BoxDecoration(
              border: Border(
                left: BorderSide(color: accent, width: 2),
                top: BorderSide(color: error ? const Color(0x66FF5D6C) : Hud.line),
                right: BorderSide(color: error ? const Color(0x66FF5D6C) : Hud.line),
                bottom: BorderSide(color: error ? const Color(0x66FF5D6C) : Hud.line),
              ),
              borderRadius: const BorderRadius.only(topRight: Radius.circular(8), bottomRight: Radius.circular(8)),
              gradient: LinearGradient(colors: [accent.withValues(alpha: .07), const Color(0x8003101C)]),
            ),
            child: Column(crossAxisAlignment: CrossAxisAlignment.start, mainAxisSize: MainAxisSize.min, children: [
              Text(error ? 'SIN CONEXIÓN' : name.toUpperCase(), style: Hud.label(size: 9.5, color: accent, spacing: .14)),
              const SizedBox(height: 5),
              if (message.text.isNotEmpty) MarkdownText(message.text, style: const TextStyle(fontSize: 14, height: 1.6, color: Color(0xFFDBF1FB))),
              for (final image in message.images)
                Padding(
                  padding: const EdgeInsets.only(top: 8),
                  child: InkWell(
                    onTap: () => onZoom(MemoryImage(image.bytes)),
                    child: ClipRRect(
                      borderRadius: BorderRadius.circular(3),
                      child: ConstrainedBox(constraints: const BoxConstraints(maxHeight: 280), child: Image.memory(image.bytes)),
                    ),
                  ),
                ),
              for (final file in message.files) _FileCard(file: file, session: session),
              if (message.confirmationId != null)
                _ConfirmCard(description: message.confirmationDescription ?? 'Ejecutar la acción pedida.', onAnswer: onAnswer),
              if (!error && message.text.isNotEmpty)
                Row(mainAxisSize: MainAxisSize.min, children: [
                  _BubbleAction(label: 'COPIAR', onTap: () {
                    Clipboard.setData(ClipboardData(text: message.text));
                    showMessage(context, 'Respuesta copiada.');
                  }),
                  _BubbleAction(label: 'ESCUCHAR', onTap: () => session.speak(message.text)),
                ]),
            ]),
          ),
        ),
      ),
    );
  }
}

class _BubbleAction extends StatelessWidget {
  const _BubbleAction({required this.label, required this.onTap});

  final String label;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) => InkWell(
        onTap: onTap,
        child: Padding(padding: const EdgeInsets.fromLTRB(0, 6, 14, 4), child: Text(label, style: Hud.label(size: 9.5, color: Hud.dim))),
      );
}

/// El Excel (u otro archivo) que generó ATLAS, con sus acciones.
class _FileCard extends StatefulWidget {
  const _FileCard({required this.file, required this.session});

  final GeneratedFile file;
  final Session session;

  @override
  State<_FileCard> createState() => _FileCardState();
}

class _FileCardState extends State<_FileCard> {
  String? _working;

  Future<void> _run(String action) async {
    setState(() => _working = action);
    final files = widget.session.files;
    try {
      switch (action) {
        case 'save':
          if (await files.save(widget.file) && mounted) showMessage(context, '${widget.file.name} guardado.');
        case 'open':
          await files.open(widget.file);
        case 'share':
          await files.share(widget.file);
      }
    } catch (error) {
      if (mounted) showMessage(context, '$error');
    } finally {
      if (mounted) setState(() => _working = null);
    }
  }

  @override
  Widget build(BuildContext context) {
    final file = widget.file;
    Widget action(String id, IconData icon, String label, {bool primary = false}) {
      final child = _working == id ? const SizedBox(width: 16, height: 16, child: CircularProgressIndicator(strokeWidth: 2)) : Icon(icon, size: 17);
      final onPressed = _working == null ? () => _run(id) : null;
      return primary
          ? FilledButton.icon(onPressed: onPressed, icon: child, label: Text(label))
          : OutlinedButton.icon(onPressed: onPressed, icon: child, label: Text(label));
    }

    return Container(
      margin: const EdgeInsets.only(top: 10),
      padding: const EdgeInsets.all(10),
      decoration: BoxDecoration(color: const Color(0xB3020C16), border: Border.all(color: Hud.line2), borderRadius: BorderRadius.circular(3)),
      child: Wrap(spacing: 8, runSpacing: 8, crossAxisAlignment: WrapCrossAlignment.center, children: [
        Row(mainAxisSize: MainAxisSize.min, children: [
          Container(
            width: 42,
            height: 42,
            alignment: Alignment.center,
            decoration: BoxDecoration(
              color: file.isSpreadsheet ? const Color(0x3321A366) : Hud.fill2,
              border: Border.all(color: file.isSpreadsheet ? const Color(0x733DDC84) : Hud.line2),
              borderRadius: BorderRadius.circular(3),
            ),
            child: Text(file.isSpreadsheet ? 'XLSX' : file.name.split('.').last.toUpperCase(),
                style: TextStyle(fontFamily: Hud.mono, fontWeight: FontWeight.w700, fontSize: 10, color: file.isSpreadsheet ? Hud.excel : Hud.cyan)),
          ),
          const SizedBox(width: 10),
          ConstrainedBox(
            constraints: const BoxConstraints(maxWidth: 230),
            child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
              Text(file.name, maxLines: 2, overflow: TextOverflow.ellipsis, style: const TextStyle(fontWeight: FontWeight.w600, fontSize: 13)),
              Text(file.sizeLabel, style: Hud.label(size: 10)),
            ]),
          ),
        ]),
        action('save', Icons.download, 'DESCARGAR', primary: true),
        action('open', Icons.open_in_new, 'ABRIR'),
        action('share', Icons.share_outlined, 'COMPARTIR'),
      ]),
    );
  }
}

class _ConfirmCard extends StatelessWidget {
  const _ConfirmCard({required this.description, required this.onAnswer});

  final String description;
  final ValueChanged<bool> onAnswer;

  @override
  Widget build(BuildContext context) {
    return Container(
      margin: const EdgeInsets.only(top: 10),
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(color: const Color(0x1FFFB547), border: Border.all(color: const Color(0x80FFB547)), borderRadius: BorderRadius.circular(3)),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Row(children: [
          const Icon(Icons.shield_outlined, color: Hud.amber, size: 18),
          const SizedBox(width: 8),
          Text('NECESITO TU CONFIRMACIÓN', style: Hud.title(size: 13, color: Hud.amber)),
        ]),
        const SizedBox(height: 6),
        Text(description),
        const SizedBox(height: 10),
        Row(children: [
          FilledButton(onPressed: () => onAnswer(true), child: const Text('CONFIRMAR')),
          const SizedBox(width: 8),
          OutlinedButton(onPressed: () => onAnswer(false), child: const Text('CANCELAR')),
        ]),
      ]),
    );
  }
}

class _Typing extends StatefulWidget {
  const _Typing();

  @override
  State<_Typing> createState() => _TypingState();
}

class _TypingState extends State<_Typing> with SingleTickerProviderStateMixin {
  late final _controller = AnimationController(vsync: this, duration: const Duration(milliseconds: 1100))..repeat();

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Align(
      alignment: Alignment.centerLeft,
      child: Container(
        margin: const EdgeInsets.only(bottom: 12),
        padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 12),
        decoration: const BoxDecoration(
          color: Color(0x9903101C),
          border: Border(left: BorderSide(color: Hud.cyan, width: 2), top: BorderSide(color: Hud.line), right: BorderSide(color: Hud.line), bottom: BorderSide(color: Hud.line)),
          borderRadius: BorderRadius.only(topRight: Radius.circular(8), bottomRight: Radius.circular(8)),
        ),
        child: AnimatedBuilder(
          animation: _controller,
          builder: (context, _) => Row(mainAxisSize: MainAxisSize.min, children: [
            for (var i = 0; i < 3; i++)
              Container(
                width: 7,
                height: 7,
                margin: const EdgeInsets.symmetric(horizontal: 3),
                decoration: BoxDecoration(
                  shape: BoxShape.circle,
                  color: Hud.cyan.withValues(alpha: ((_controller.value * 3 - i) % 3) < 1 ? 1 : .25),
                  boxShadow: const [BoxShadow(color: Hud.cyan, blurRadius: 6)],
                ),
              ),
          ]),
        ),
      ),
    );
  }
}
