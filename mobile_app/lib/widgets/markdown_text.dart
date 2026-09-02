import 'package:flutter/gestures.dart';
import 'package:flutter/material.dart';
import 'package:url_launcher/url_launcher.dart';

import '../theme/atlas_theme.dart';

/// Markdown a widgets para las burbujas del chat — el equivalente Dart de
/// shared/markdown.js, que hace lo mismo para el dashboard y la PWA.
///
/// Escrito a mano por la misma razón que el de JS: es el único lugar de la
/// app que lo necesita y las opciones de pub.dev traen un parser CommonMark
/// entero para renderizar negritas y links. Se cubre lo que el modelo
/// realmente devuelve: encabezados, listas, negrita/cursiva/tachado, código
/// y enlaces.
///
/// Diferencia conocida con shared/markdown.js: allá un link de YouTube se
/// convierte en una tarjeta con miniatura; acá se muestra como enlace
/// normal (haría falta bajar la imagen de img.youtube.com, que es otra cosa).
class MarkdownText extends StatelessWidget {
  final String text;
  final TextStyle baseStyle;

  const MarkdownText({super.key, required this.text, required this.baseStyle});

  @override
  Widget build(BuildContext context) {
    final blocks = _parseBlocks(text);
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      mainAxisSize: MainAxisSize.min,
      children: [
        for (var i = 0; i < blocks.length; i++) ...[
          if (i > 0) const SizedBox(height: 6),
          blocks[i].build(baseStyle),
        ],
      ],
    );
  }
}

// ---------- Bloques ----------

abstract class _Block {
  Widget build(TextStyle base);
}

class _Paragraph extends _Block {
  final String text;
  _Paragraph(this.text);

  @override
  Widget build(TextStyle base) => Text.rich(TextSpan(children: _parseInline(text, base)), style: base);
}

class _Heading extends _Block {
  final int level; // 1..6 tal como lo escribió el modelo
  final String text;
  _Heading(this.level, this.text);

  @override
  Widget build(TextStyle base) {
    // Igual que en shared/markdown.js: un h1 del modelo se degrada, acá no
    // hay una jerarquía de documento que respetar y un título gigante
    // dentro de una burbuja queda fuera de escala.
    final size = (base.fontSize ?? 14) + (level <= 2 ? 3 : 1);
    final style = base.copyWith(fontSize: size, fontWeight: FontWeight.w700, color: Colors.white);
    return Text.rich(TextSpan(children: _parseInline(text, style)), style: style);
  }
}

class _ListItem {
  /// El número tal como lo escribió el modelo, o null para una viñeta. Se
  /// conserva en vez de renumerar desde 1: el modelo suele separar los
  /// ítems con una línea en blanco, y eso corta la lista en varios bloques
  /// — renumerando, un "1. 2. 3." se vería como "1. 1. 1.".
  final String? number;
  final String text;
  _ListItem(this.number, this.text);
}

class _ListBlock extends _Block {
  final List<_ListItem> items;
  _ListBlock(this.items);

  @override
  Widget build(TextStyle base) {
    final markerStyle = base.copyWith(color: AtlasColors.textDim);
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      mainAxisSize: MainAxisSize.min,
      children: [
        for (final item in items)
          Padding(
            padding: const EdgeInsets.only(bottom: 3),
            child: Row(
              crossAxisAlignment: CrossAxisAlignment.start,
              mainAxisSize: MainAxisSize.min,
              children: [
                SizedBox(
                  width: 22,
                  child: Text(item.number == null ? '•' : '${item.number}.', style: markerStyle),
                ),
                Flexible(
                  child: Text.rich(TextSpan(children: _parseInline(item.text, base)), style: base),
                ),
              ],
            ),
          ),
      ],
    );
  }
}

class _CodeBlock extends _Block {
  final String code;
  _CodeBlock(this.code);

  @override
  Widget build(TextStyle base) {
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 8),
      decoration: BoxDecoration(
        color: AtlasColors.bg,
        borderRadius: BorderRadius.circular(8),
        border: Border.all(color: AtlasColors.border),
      ),
      child: SingleChildScrollView(
        scrollDirection: Axis.horizontal,
        child: Text(
          code,
          style: base.copyWith(fontFamily: 'monospace', fontSize: (base.fontSize ?? 14) - 1),
        ),
      ),
    );
  }
}

final _fenceRe = RegExp(r'^\s*```');
final _headingRe = RegExp(r'^\s{0,3}(#{1,6})\s+(.*)$');
final _bulletRe = RegExp(r'^\s*[-*+]\s+');
final _orderedRe = RegExp(r'^\s*(\d+)\.\s+');

List<_Block> _parseBlocks(String text) {
  final lines = text.split('\n');
  final blocks = <_Block>[];
  final paragraph = <String>[];

  void flushParagraph() {
    if (paragraph.isEmpty) return;
    blocks.add(_Paragraph(paragraph.join('\n')));
    paragraph.clear();
  }

  for (var i = 0; i < lines.length; i++) {
    final line = lines[i];

    if (_fenceRe.hasMatch(line)) {
      flushParagraph();
      final code = <String>[];
      i++;
      // Un bloque sin cierre (pasa mientras el streaming va a medio camino)
      // se muestra igual con lo que haya llegado, en vez de tragarse el resto.
      while (i < lines.length && !_fenceRe.hasMatch(lines[i])) {
        code.add(lines[i]);
        i++;
      }
      blocks.add(_CodeBlock(code.join('\n')));
      continue;
    }

    if (line.trim().isEmpty) {
      flushParagraph();
      continue;
    }

    final heading = _headingRe.firstMatch(line);
    if (heading != null) {
      flushParagraph();
      blocks.add(_Heading(heading.group(1)!.length, heading.group(2)!));
      continue;
    }

    final ordered = _orderedRe.hasMatch(line);
    if (ordered || _bulletRe.hasMatch(line)) {
      flushParagraph();
      final items = <_ListItem>[];
      final re = ordered ? _orderedRe : _bulletRe;
      while (i < lines.length && re.hasMatch(lines[i])) {
        final match = re.firstMatch(lines[i])!;
        items.add(_ListItem(
          ordered ? match.group(1) : null,
          lines[i].substring(match.end),
        ));
        i++;
      }
      i--; // el for vuelve a incrementar
      blocks.add(_ListBlock(items));
      continue;
    }

    paragraph.add(line);
  }

  flushParagraph();
  return blocks;
}

// ---------- Inline ----------

/// Las reglas se prueban todas y gana la que matchee más a la izquierda, así
/// el orden de esta lista solo desempata en la misma posición: por eso el
/// código va primero (adentro no se interpreta nada) y ***/** antes que *.
final _inlineRules = <_InlineRule>[
  _InlineRule(RegExp(r'`([^`\n]+)`'), _InlineKind.code),
  _InlineRule(RegExp(r'\[([^\]]+)\]\((https?://[^\s)]+)\)'), _InlineKind.link),
  _InlineRule(RegExp(r'https?://[^\s<]+[^\s<.,;:!?)]'), _InlineKind.bareLink),
  _InlineRule(RegExp(r'(\*\*\*|___)(.+?)\1'), _InlineKind.boldItalic),
  _InlineRule(RegExp(r'(\*\*|__)(.+?)\1'), _InlineKind.bold),
  _InlineRule(RegExp(r'~~(.+?)~~'), _InlineKind.strike),
  // Cursiva: se exige que no haya carácter de palabra alrededor, para no
  // romper identificadores como get_system_info. El carácter previo entra
  // en el match y se vuelve a emitir como texto plano.
  _InlineRule(RegExp(r'(^|[\s(])[*_]([^*_\n]+)[*_](?=[\s.,;:!?)]|$)'), _InlineKind.italic),
];

enum _InlineKind { code, link, bareLink, boldItalic, bold, strike, italic }

class _InlineRule {
  final RegExp pattern;
  final _InlineKind kind;
  _InlineRule(this.pattern, this.kind);
}

List<InlineSpan> _parseInline(String text, TextStyle style) {
  if (text.isEmpty) return const [];

  RegExpMatch? best;
  _InlineKind? bestKind;
  for (final rule in _inlineRules) {
    final match = rule.pattern.firstMatch(text);
    if (match == null) continue;
    if (best == null || match.start < best.start) {
      best = match;
      bestKind = rule.kind;
    }
  }

  if (best == null) return [TextSpan(text: text, style: style)];

  final spans = <InlineSpan>[];
  if (best.start > 0) {
    spans.add(TextSpan(text: text.substring(0, best.start), style: style));
  }

  switch (bestKind!) {
    case _InlineKind.code:
      spans.add(TextSpan(
        text: best.group(1),
        style: style.copyWith(
          fontFamily: 'monospace',
          fontSize: (style.fontSize ?? 14) - 1,
          backgroundColor: AtlasColors.bg,
        ),
      ));
      break;
    case _InlineKind.link:
      spans.add(_linkSpan(best.group(2)!, best.group(1)!, style));
      break;
    case _InlineKind.bareLink:
      spans.add(_linkSpan(best.group(0)!, best.group(0)!, style));
      break;
    case _InlineKind.boldItalic:
      spans.addAll(_parseInline(
        best.group(2)!,
        style.copyWith(fontWeight: FontWeight.w600, fontStyle: FontStyle.italic, color: Colors.white),
      ));
      break;
    case _InlineKind.bold:
      spans.addAll(_parseInline(
        best.group(2)!,
        style.copyWith(fontWeight: FontWeight.w600, color: Colors.white),
      ));
      break;
    case _InlineKind.strike:
      spans.addAll(_parseInline(
        best.group(1)!,
        style.copyWith(decoration: TextDecoration.lineThrough, color: style.color?.withValues(alpha: 0.6)),
      ));
      break;
    case _InlineKind.italic:
      if (best.group(1)!.isNotEmpty) {
        spans.add(TextSpan(text: best.group(1), style: style));
      }
      spans.addAll(_parseInline(best.group(2)!, style.copyWith(fontStyle: FontStyle.italic)));
      break;
  }

  spans.addAll(_parseInline(text.substring(best.end), style));
  return spans;
}

InlineSpan _linkSpan(String url, String label, TextStyle style) {
  return TextSpan(
    text: label,
    style: style.copyWith(color: AtlasColors.accent, decoration: TextDecoration.underline),
    recognizer: TapGestureRecognizer()
      ..onTap = () {
        // El link puede venir de una búsqueda web o de lo que el modelo
        // haya recordado, así que puede no abrir: falla en silencio en vez
        // de romper la burbuja.
        launchUrl(Uri.parse(url), mode: LaunchMode.externalApplication).catchError((_) => false);
      },
  );
}
