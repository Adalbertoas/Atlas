import 'package:flutter/material.dart';

import 'theme.dart';

/// Markdown básico de las respuestas de ATLAS: títulos, listas, **negrita**,
/// *cursiva* y `código`. Lo mismo que renderiza el escritorio (RichText.tsx).
class MarkdownText extends StatelessWidget {
  const MarkdownText(this.text, {super.key, this.style});

  final String text;
  final TextStyle? style;

  @override
  Widget build(BuildContext context) {
    final base = style ?? const TextStyle(fontSize: 15, height: 1.45, color: Hud.text);
    final blocks = <Widget>[];
    for (final raw in text.trim().split('\n')) {
      final line = raw.trimRight();
      if (line.trim().isEmpty) {
        blocks.add(const SizedBox(height: 6));
        continue;
      }
      final heading = RegExp(r'^(#{1,4})\s+(.*)$').firstMatch(line);
      final bullet = RegExp(r'^\s*[-*•]\s+(.*)$').firstMatch(line);
      final numbered = RegExp(r'^\s*(\d+)[.)]\s+(.*)$').firstMatch(line);
      if (heading != null) {
        final size = 19.0 - heading.group(1)!.length;
        blocks.add(Padding(
          padding: const EdgeInsets.only(top: 6, bottom: 2),
          child: Text.rich(_inline(heading.group(2)!, base.copyWith(fontSize: size, fontWeight: FontWeight.w700, color: Hud.cyan))),
        ));
      } else if (bullet != null || numbered != null) {
        final marker = bullet != null ? '•' : '${numbered!.group(1)}.';
        final content = bullet?.group(1) ?? numbered!.group(2)!;
        blocks.add(Padding(
          padding: const EdgeInsets.only(left: 4, top: 1, bottom: 1),
          child: Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
            SizedBox(width: 22, child: Text(marker, style: base.copyWith(color: Hud.cyan))),
            Expanded(child: Text.rich(_inline(content, base))),
          ]),
        ));
      } else {
        blocks.add(Text.rich(_inline(line, base)));
      }
    }
    return Column(crossAxisAlignment: CrossAxisAlignment.start, children: blocks);
  }

  static final _token = RegExp(r'(\*\*[^*]+\*\*|`[^`]+`|\*[^*\s][^*]*\*)');

  TextSpan _inline(String text, TextStyle base) {
    final spans = <InlineSpan>[];
    var index = 0;
    for (final match in _token.allMatches(text)) {
      if (match.start > index) spans.add(TextSpan(text: text.substring(index, match.start)));
      final token = match.group(0)!;
      if (token.startsWith('**')) {
        spans.add(TextSpan(text: token.substring(2, token.length - 2), style: const TextStyle(fontWeight: FontWeight.w700)));
      } else if (token.startsWith('`')) {
        spans.add(TextSpan(
          text: token.substring(1, token.length - 1),
          style: const TextStyle(fontFamily: 'monospace', backgroundColor: Hud.fill2, color: Hud.cyan),
        ));
      } else {
        spans.add(TextSpan(text: token.substring(1, token.length - 1), style: const TextStyle(fontStyle: FontStyle.italic)));
      }
      index = match.end;
    }
    if (index < text.length) spans.add(TextSpan(text: text.substring(index)));
    return TextSpan(style: base, children: spans);
  }
}
