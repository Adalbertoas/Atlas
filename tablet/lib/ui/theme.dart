import 'package:flutter/material.dart';

/// Colores y fuentes del HUD de ATLAS (los mismos que jarvis.css del escritorio).
abstract final class Hud {
  static const background = Color(0xFF01070E);
  static const cyan = Color(0xFF3FE6FF);
  static const cyan2 = Color(0xFF14B8E6);
  static const deep = Color(0xFF0A7FA6);
  static const text = Color(0xFFDCF6FF);
  static const bright = Color(0xFFEAFCFF);
  static const muted = Color(0xFF7FA5BA);
  static const dim = Color(0xFF4D7186);
  static const amber = Color(0xFFFFB547);
  static const red = Color(0xFFFF5D6C);
  static const green = Color(0xFF3DF0A6);
  static const excel = Color(0xFF3DDC84);
  static const line = Color(0x293FE6FF); // rgba(63,230,255,.16)
  static const line2 = Color(0x523FE6FF); // .32
  static const fill = Color(0x0F3FE6FF); // .06
  static const fill2 = Color(0x1F3FE6FF); // .12
  static const panel = Color(0xD6030D17); // rgba(3,13,23,.84)
  static const panel2 = Color(0xCC020911);

  static const display = 'Rajdhani';
  static const mono = 'JetBrainsMono';

  /// Títulos de panel y navegación: Rajdhani en mayúsculas con espaciado.
  static TextStyle title({double size = 14, Color color = const Color(0xFFE3F9FF), FontWeight weight = FontWeight.w700}) =>
      TextStyle(fontFamily: display, fontSize: size, fontWeight: weight, letterSpacing: size * .14, color: color, height: 1.1);

  /// Etiquetas técnicas: JetBrains Mono chico en mayúsculas.
  static TextStyle label({double size = 10, Color color = muted, double spacing = .08}) =>
      TextStyle(fontFamily: mono, fontSize: size, letterSpacing: size * spacing, color: color, height: 1.2);

  static const glow = [Shadow(color: Color(0x993FE6FF), blurRadius: 10)];
}

ThemeData atlasTheme() {
  const scheme = ColorScheme.dark(
    primary: Hud.cyan,
    onPrimary: Color(0xFF00222B),
    secondary: Hud.amber,
    surface: Color(0xFF06182A),
    onSurface: Hud.text,
    error: Hud.red,
  );
  final border = OutlineInputBorder(borderRadius: BorderRadius.circular(3), borderSide: const BorderSide(color: Hud.line2));
  return ThemeData(
    useMaterial3: true,
    colorScheme: scheme,
    scaffoldBackgroundColor: Hud.background,
    textTheme: Typography.whiteMountainView.apply(bodyColor: Hud.text, displayColor: Hud.text),
    dividerColor: Hud.line,
    splashFactory: InkRipple.splashFactory,
    inputDecorationTheme: InputDecorationTheme(
      filled: true,
      fillColor: const Color(0xD9020C16),
      hintStyle: const TextStyle(color: Hud.dim),
      labelStyle: const TextStyle(color: Hud.muted),
      border: border,
      enabledBorder: border,
      focusedBorder: border.copyWith(borderSide: const BorderSide(color: Hud.cyan, width: 1.2)),
      contentPadding: const EdgeInsets.symmetric(horizontal: 14, vertical: 13),
    ),
    filledButtonTheme: FilledButtonThemeData(
      style: FilledButton.styleFrom(
        backgroundColor: const Color(0x403FE6FF),
        foregroundColor: Colors.white,
        side: const BorderSide(color: Hud.cyan),
        textStyle: const TextStyle(fontFamily: Hud.display, fontWeight: FontWeight.w700, letterSpacing: 1.2, fontSize: 14),
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(3)),
        padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
      ),
    ),
    outlinedButtonTheme: OutlinedButtonThemeData(
      style: OutlinedButton.styleFrom(
        foregroundColor: Hud.text,
        side: const BorderSide(color: Hud.line2),
        textStyle: const TextStyle(fontFamily: Hud.display, fontWeight: FontWeight.w600, letterSpacing: .8, fontSize: 14),
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(3)),
      ),
    ),
    textButtonTheme: TextButtonThemeData(
      style: TextButton.styleFrom(
        foregroundColor: Hud.cyan,
        textStyle: const TextStyle(fontFamily: Hud.mono, fontSize: 11, letterSpacing: .6),
      ),
    ),
    switchTheme: SwitchThemeData(
      thumbColor: WidgetStateProperty.resolveWith((s) => s.contains(WidgetState.selected) ? Hud.cyan : Hud.muted),
      trackColor: WidgetStateProperty.resolveWith((s) => s.contains(WidgetState.selected) ? const Color(0x553FE6FF) : Hud.fill2),
      trackOutlineColor: const WidgetStatePropertyAll(Hud.line2),
    ),
    sliderTheme: const SliderThemeData(activeTrackColor: Hud.cyan, inactiveTrackColor: Hud.fill2, thumbColor: Hud.cyan),
    snackBarTheme: const SnackBarThemeData(
      backgroundColor: Color(0xF5020E19),
      contentTextStyle: TextStyle(color: Hud.text, fontFamily: Hud.mono, fontSize: 12),
      behavior: SnackBarBehavior.floating,
      shape: RoundedRectangleBorder(side: BorderSide(color: Hud.cyan), borderRadius: BorderRadius.all(Radius.circular(3))),
    ),
    dialogTheme: const DialogThemeData(
      backgroundColor: Color(0xFA04111E),
      shape: RoundedRectangleBorder(side: BorderSide(color: Hud.line2), borderRadius: BorderRadius.all(Radius.circular(4))),
    ),
    bottomSheetTheme: const BottomSheetThemeData(backgroundColor: Color(0xFA04111E)),
    progressIndicatorTheme: const ProgressIndicatorThemeData(color: Hud.cyan),
  );
}

/// Ventana del HUD: degradado translúcido, escuadras en las cuatro esquinas,
/// barra de título con acento cian y líneas de barrido muy tenues.
class HudPanel extends StatelessWidget {
  const HudPanel({
    super.key,
    this.title,
    this.icon,
    this.trailing,
    required this.child,
    this.padding = const EdgeInsets.all(14),
    this.active = false,
    this.onClose,
  });

  final String? title;
  final IconData? icon;
  final Widget? trailing;
  final Widget child;
  final EdgeInsets padding;
  final bool active;
  final VoidCallback? onClose;

  @override
  Widget build(BuildContext context) {
    return CustomPaint(
      foregroundPainter: _PanelChrome(active: active),
      child: Container(
        decoration: BoxDecoration(
          gradient: const LinearGradient(begin: Alignment.topLeft, end: Alignment.bottomRight, colors: [Hud.panel, Hud.panel2]),
          border: Border.all(color: active ? Hud.line2 : Hud.line),
          borderRadius: BorderRadius.circular(4),
          boxShadow: [
            const BoxShadow(color: Color(0x73000000), blurRadius: 30, offset: Offset(0, 14)),
            if (active) const BoxShadow(color: Color(0x143FE6FF), blurRadius: 24),
          ],
        ),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          mainAxisSize: MainAxisSize.min,
          children: [
            if (title != null) _TitleBar(title: title!, icon: icon, trailing: trailing, active: active, onClose: onClose),
            Flexible(child: Padding(padding: padding, child: child)),
          ],
        ),
      ),
    );
  }
}

class _TitleBar extends StatelessWidget {
  const _TitleBar({required this.title, this.icon, this.trailing, required this.active, this.onClose});

  final String title;
  final IconData? icon;
  final Widget? trailing;
  final bool active;
  final VoidCallback? onClose;

  @override
  Widget build(BuildContext context) {
    return Container(
      height: 40,
      padding: const EdgeInsets.only(left: 14, right: 6),
      decoration: const BoxDecoration(
        border: Border(bottom: BorderSide(color: Hud.line)),
        gradient: LinearGradient(colors: [Color(0x123FE6FF), Colors.transparent], stops: [0, .6]),
      ),
      child: Stack(clipBehavior: Clip.none, children: [
        Positioned(
          left: 0,
          bottom: -1,
          child: Container(
            width: active ? 64 : 42,
            height: 1,
            decoration: BoxDecoration(
              color: Hud.cyan.withValues(alpha: active ? 1 : .5),
              boxShadow: const [BoxShadow(color: Hud.cyan, blurRadius: 8)],
            ),
          ),
        ),
        Row(children: [
          if (icon != null) ...[
            Icon(icon, size: 16, color: Hud.cyan, shadows: const [Shadow(color: Color(0x803FE6FF), blurRadius: 6)]),
            const SizedBox(width: 9),
          ],
          Expanded(child: Text(title.toUpperCase(), maxLines: 1, overflow: TextOverflow.ellipsis, style: Hud.title())),
          ?trailing,
          if (onClose != null) ...[
            const SizedBox(width: 4),
            _WindowButton(icon: Icons.close, onTap: onClose!),
          ] else if (trailing == null) ...[
            // Decorativos, como en el escritorio; si el panel tiene acciones propias, se omiten.
            const SizedBox(width: 4),
            const _WindowButton(icon: Icons.remove),
            const _WindowButton(icon: Icons.crop_square),
          ],
        ]),
      ]),
    );
  }
}

/// Botones de ventana del escritorio; en la tablet son decorativos salvo cerrar.
class _WindowButton extends StatelessWidget {
  const _WindowButton({required this.icon, this.onTap});

  final IconData icon;
  final VoidCallback? onTap;

  @override
  Widget build(BuildContext context) {
    return InkWell(
      onTap: onTap,
      borderRadius: BorderRadius.circular(2),
      child: SizedBox(width: 26, height: 24, child: Icon(icon, size: 12, color: Hud.dim)),
    );
  }
}

/// Escuadras de las esquinas + líneas de barrido.
class _PanelChrome extends CustomPainter {
  _PanelChrome({required this.active});

  final bool active;

  @override
  void paint(Canvas canvas, Size size) {
    final scan = Paint()..color = const Color(0x063FE6FF);
    for (var y = 0.0; y < size.height; y += 3) {
      canvas.drawRect(Rect.fromLTWH(0, y, size.width, 1), scan);
    }
    final paint = Paint()
      ..color = Hud.cyan.withValues(alpha: active ? 1 : .75)
      ..strokeWidth = 1.5
      ..style = PaintingStyle.stroke;
    if (active) paint.maskFilter = const MaskFilter.blur(BlurStyle.solid, 2);
    const l = 14.0;
    final w = size.width, h = size.height;
    final path = Path()
      ..moveTo(0, l)
      ..lineTo(0, 0)
      ..lineTo(l, 0)
      ..moveTo(w - l, 0)
      ..lineTo(w, 0)
      ..lineTo(w, l)
      ..moveTo(w, h - l)
      ..lineTo(w, h)
      ..lineTo(w - l, h)
      ..moveTo(l, h)
      ..lineTo(0, h)
      ..lineTo(0, h - l);
    canvas.drawPath(path, paint);
  }

  @override
  bool shouldRepaint(_PanelChrome old) => old.active != active;
}

/// Botón con estilo de "chip" del HUD (como los del estado del núcleo).
class HudChip extends StatelessWidget {
  const HudChip({super.key, required this.label, this.icon, this.onTap, this.selected = false, this.color = Hud.cyan});

  final String label;
  final IconData? icon;
  final VoidCallback? onTap;
  final bool selected;
  final Color color;

  @override
  Widget build(BuildContext context) {
    return InkWell(
      onTap: onTap,
      borderRadius: BorderRadius.circular(3),
      child: Container(
        padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 7),
        decoration: BoxDecoration(
          color: selected ? color.withValues(alpha: .16) : const Color(0x99020E19),
          border: Border.all(color: selected ? color : Hud.line2),
          borderRadius: BorderRadius.circular(3),
          boxShadow: selected ? [BoxShadow(color: color.withValues(alpha: .25), blurRadius: 10)] : null,
        ),
        child: Row(mainAxisSize: MainAxisSize.min, children: [
          if (icon != null) ...[Icon(icon, size: 14, color: selected ? color : Hud.muted), const SizedBox(width: 6)],
          Flexible(
            child: Text(label,
                overflow: TextOverflow.ellipsis,
                style: Hud.label(size: 9.5, color: selected ? Colors.white : Hud.text, spacing: .02)),
          ),
        ]),
      ),
    );
  }
}

void showMessage(BuildContext context, String text) {
  ScaffoldMessenger.of(context)
    ..hideCurrentSnackBar()
    ..showSnackBar(SnackBar(content: Text(text)));
}
