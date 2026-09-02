import 'package:flutter/material.dart';

import '../models/chat_message.dart';
import '../services/api_client.dart';
import '../theme/atlas_theme.dart';
import '../widgets/markdown_text.dart';

class ChatScreen extends StatefulWidget {
  final ApiClient apiClient;
  const ChatScreen({super.key, required this.apiClient});

  @override
  State<ChatScreen> createState() => _ChatScreenState();
}

class _ChatScreenState extends State<ChatScreen> {
  final _messages = <ChatMessage>[];
  final _inputController = TextEditingController();
  final _scrollController = ScrollController();
  String? _conversationId;
  bool _sending = false;

  @override
  void dispose() {
    _inputController.dispose();
    _scrollController.dispose();
    super.dispose();
  }

  void _scrollToBottom() {
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!_scrollController.hasClients) return;
      _scrollController.animateTo(
        _scrollController.position.maxScrollExtent,
        duration: const Duration(milliseconds: 200),
        curve: Curves.easeOut,
      );
    });
  }

  Future<void> _send() async {
    final text = _inputController.text.trim();
    if (text.isEmpty || _sending) return;
    _inputController.clear();

    setState(() {
      _messages.add(ChatMessage(role: ChatRole.user, initialText: text));
      _sending = true;
    });
    _scrollToBottom();

    final atlasMessage = ChatMessage(role: ChatRole.atlas, isTyping: true);
    setState(() => _messages.add(atlasMessage));
    _scrollToBottom();

    try {
      await for (final event in widget.apiClient.sendChatStream(text, conversationId: _conversationId)) {
        switch (event.type) {
          case 'token':
            if (event.text != null) {
              setState(() => atlasMessage.appendText(event.text!));
              _scrollToBottom();
            }
            break;
          case 'tool_call':
            setState(() {
              atlasMessage.isTyping = false;
              atlasMessage.toolHint = 'usando ${event.toolDescription ?? event.toolName ?? ''}…';
            });
            _scrollToBottom();
            break;
          case 'confirmation':
            _conversationId = event.conversationId ?? _conversationId;
            setState(() => _messages.remove(atlasMessage));
            await _handleConfirmation(event.confirmationId!, event.confirmationDescription);
            break;
          case 'done':
            _conversationId = event.conversationId ?? _conversationId;
            if (event.reply != null) {
              setState(() => atlasMessage.setFullText(event.reply!));
            }
            break;
        }
      }
    } on ApiException catch (e) {
      setState(() => atlasMessage.setFullText('(error: ${e.message})'));
    } catch (e) {
      setState(() => atlasMessage.setFullText('(error: no se pudo conectar al servidor)'));
    } finally {
      if (mounted) setState(() => _sending = false);
      _scrollToBottom();
    }
  }

  Future<void> _handleConfirmation(String confirmationId, String? description) async {
    final approve = await showDialog<bool>(
      context: context,
      builder: (context) => AlertDialog(
        backgroundColor: AtlasColors.panel2,
        title: const Text('Confirmar acción', style: TextStyle(color: AtlasColors.text)),
        content: Text(
          description ?? '¿Confirmar esta acción?',
          style: const TextStyle(color: AtlasColors.textDim),
        ),
        actions: [
          TextButton(onPressed: () => Navigator.pop(context, false), child: const Text('Cancelar')),
          ElevatedButton(onPressed: () => Navigator.pop(context, true), child: const Text('Confirmar')),
        ],
      ),
    );

    final resultMessage = ChatMessage(role: ChatRole.atlas);
    setState(() => _messages.add(resultMessage));

    try {
      final result = await widget.apiClient.confirmAction(confirmationId, approve ?? false);
      setState(() => resultMessage.setFullText(result.reply ?? (approve == true ? 'Listo.' : 'Acción cancelada.')));
    } on ApiException catch (e) {
      setState(() => resultMessage.setFullText('(error: ${e.message})'));
    }
    _scrollToBottom();
  }

  @override
  Widget build(BuildContext context) {
    return Column(
      children: [
        Expanded(
          child: _messages.isEmpty
              ? const Center(
                  child: Text('Escribile a ATLAS…', style: TextStyle(color: AtlasColors.textFaint)),
                )
              : ListView.builder(
                  controller: _scrollController,
                  padding: const EdgeInsets.all(14),
                  itemCount: _messages.length,
                  itemBuilder: (context, index) => _ChatBubble(message: _messages[index]),
                ),
        ),
        _ChatInputBar(controller: _inputController, sending: _sending, onSend: _send),
      ],
    );
  }
}

class _ChatBubble extends StatelessWidget {
  final ChatMessage message;
  const _ChatBubble({required this.message});

  @override
  Widget build(BuildContext context) {
    final isUser = message.role == ChatRole.user;
    return Align(
      alignment: isUser ? Alignment.centerRight : Alignment.centerLeft,
      child: Container(
        constraints: BoxConstraints(maxWidth: MediaQuery.of(context).size.width * 0.78),
        margin: const EdgeInsets.symmetric(vertical: 5),
        padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 10),
        decoration: BoxDecoration(
          color: isUser ? AtlasColors.accent : AtlasColors.panel,
          borderRadius: BorderRadius.only(
            topLeft: const Radius.circular(14),
            topRight: const Radius.circular(14),
            bottomLeft: Radius.circular(isUser ? 14 : 4),
            bottomRight: Radius.circular(isUser ? 4 : 14),
          ),
          border: isUser ? null : Border.all(color: AtlasColors.border),
        ),
        child: message.isTyping ? const _TypingDots() : _bubbleContent(),
      ),
    );
  }

  Widget _bubbleContent() {
    final isUser = message.role == ChatRole.user;
    final textColor = isUser ? AtlasColors.accentOn : AtlasColors.text;
    final textStyle = TextStyle(color: textColor, fontSize: 14.5, height: 1.45);
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      mainAxisSize: MainAxisSize.min,
      children: [
        // Solo lo que dice ATLAS se interpreta como Markdown; lo que
        // escribiste vos se muestra literal, igual que en el dashboard
        // (allá la burbuja del usuario usa textContent y no innerHTML).
        if (isUser)
          Text(message.text, style: textStyle)
        else
          MarkdownText(text: message.text, baseStyle: textStyle),
        if (message.toolHint != null) ...[
          const SizedBox(height: 6),
          Container(
            padding: const EdgeInsets.only(top: 6),
            decoration: const BoxDecoration(
              border: Border(top: BorderSide(color: AtlasColors.border, style: BorderStyle.solid)),
            ),
            child: Row(
              mainAxisSize: MainAxisSize.min,
              children: [
                const Icon(Icons.bolt, size: 13, color: AtlasColors.accent),
                const SizedBox(width: 5),
                Flexible(
                  child: Text(
                    message.toolHint!,
                    style: const TextStyle(color: AtlasColors.textFaint, fontSize: 12, fontStyle: FontStyle.italic),
                  ),
                ),
              ],
            ),
          ),
        ],
      ],
    );
  }
}

class _TypingDots extends StatefulWidget {
  const _TypingDots();

  @override
  State<_TypingDots> createState() => _TypingDotsState();
}

class _TypingDotsState extends State<_TypingDots> with SingleTickerProviderStateMixin {
  late final AnimationController _controller;

  @override
  void initState() {
    super.initState();
    _controller = AnimationController(vsync: this, duration: const Duration(milliseconds: 1200))..repeat();
  }

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return SizedBox(
      width: 34,
      height: 14,
      child: AnimatedBuilder(
        animation: _controller,
        builder: (context, _) {
          return Row(
            mainAxisAlignment: MainAxisAlignment.spaceBetween,
            children: List.generate(3, (i) {
              final t = (_controller.value - i * 0.15) % 1.0;
              final opacity = 0.35 + 0.65 * (t < 0.5 ? t * 2 : (1 - t) * 2).clamp(0.0, 1.0);
              return Opacity(
                opacity: opacity,
                child: Container(
                  width: 6,
                  height: 6,
                  decoration: const BoxDecoration(color: AtlasColors.textDim, shape: BoxShape.circle),
                ),
              );
            }),
          );
        },
      ),
    );
  }
}

class _ChatInputBar extends StatelessWidget {
  final TextEditingController controller;
  final bool sending;
  final VoidCallback onSend;

  const _ChatInputBar({required this.controller, required this.sending, required this.onSend});

  @override
  Widget build(BuildContext context) {
    return Container(
      decoration: const BoxDecoration(
        color: AtlasColors.bg,
        border: Border(top: BorderSide(color: AtlasColors.border)),
      ),
      child: SafeArea(
        top: false,
        child: Padding(
          padding: const EdgeInsets.fromLTRB(12, 10, 12, 10),
          child: Row(
            children: [
              Expanded(
                child: TextField(
                  controller: controller,
                  style: const TextStyle(fontSize: 14.5),
                  decoration: const InputDecoration(
                    hintText: 'Escribile a ATLAS…',
                    isDense: true,
                    contentPadding: EdgeInsets.symmetric(horizontal: 15, vertical: 13),
                  ),
                  textInputAction: TextInputAction.send,
                  onSubmitted: (_) => onSend(),
                  enabled: !sending,
                ),
              ),
              const SizedBox(width: 8),
              IconButton.filled(
                onPressed: sending ? null : onSend,
                icon: const Icon(Icons.send_rounded, size: 20),
                style: IconButton.styleFrom(
                  backgroundColor: AtlasColors.accent,
                  foregroundColor: AtlasColors.accentOn,
                  disabledBackgroundColor: AtlasColors.panel2,
                  disabledForegroundColor: AtlasColors.textFaint,
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}
