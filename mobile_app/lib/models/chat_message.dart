enum ChatRole { user, atlas }

/// Un mensaje del chat. `text` es mutable (`StringBuffer` en vez de String
/// final) porque las burbujas de ATLAS se van llenando token a token
/// mientras llega el streaming — mismo motivo que dashboard/app.js reasigna
/// `atlasBubble.innerHTML` en cada evento "token".
class ChatMessage {
  final ChatRole role;
  final StringBuffer _text = StringBuffer();
  bool isTyping; // true = mostrar el indicador de "escribiendo…", sin texto real todavía
  String? toolHint; // "usando <tool>…" mientras corre una tool, se limpia con el próximo token

  ChatMessage({required this.role, String initialText = '', this.isTyping = false}) {
    _text.write(initialText);
  }

  String get text => _text.toString();

  void appendText(String chunk) {
    _text.write(chunk);
    isTyping = false;
    toolHint = null;
  }

  void setFullText(String value) {
    _text
      ..clear()
      ..write(value);
    isTyping = false;
  }
}
