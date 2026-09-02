import 'package:flutter/material.dart';

/// Misma paleta que dashboard/styles.css (:root) — fondo oscuro azulado,
/// acento cian. Un solo lugar con los valores, igual criterio que
/// atlas_desktop/theme.py en el cliente de escritorio (Tkinter tampoco
/// tiene variables CSS, cada widget necesita sus colores a mano).
class AtlasColors {
  static const bg = Color(0xFF060A10);
  static const panel = Color(0xFF0B1119);
  static const panel2 = Color(0xFF0E1620);
  static const border = Color(0xFF16202C);
  static const borderBright = Color(0xFF1D2B3A);

  static const text = Color(0xFFE6EDF5);
  static const textDim = Color(0xFF7B8896);
  static const textFaint = Color(0xFF55616E);

  static const accent = Color(0xFF22D3EE);
  static const accentOn = Color(0xFF04141A); // texto sobre fondo de acento sólido

  static const ok = Color(0xFF34D399);
  static const warn = Color(0xFFFBBF24);
  static const danger = Color(0xFFF87171);

  /// Equivalentes de --accent-soft / --accent-line / --accent-glow. En CSS
  /// son rgba() literales; acá se derivan del acento para que un cambio de
  /// `accent` arrastre a los cuatro.
  static const accentSoft = Color(0x1F22D3EE); // 12%
  static const accentLine = Color(0x4722D3EE); // 28%
  static const accentGlow = Color(0x5922D3EE); // 35%
}

/// --radius y --radius-sm de dashboard/styles.css. Las tarjetas y los
/// campos usan el chico; los paneles y las burbujas del chat, el grande.
class AtlasRadius {
  static const card = 10.0;
  static const panel = 14.0;
}

/// --font-body / --font-display. Inter para todo el cuerpo; Space Grotesk
/// reservada para marca y títulos, igual que en el dashboard.
class AtlasFonts {
  static const body = 'Inter';
  static const display = 'SpaceGrotesk';
}

/// El degradado de `.panel` (linear-gradient(160deg, --panel-2, --panel)).
/// 160° en CSS se mide desde arriba en sentido horario, así que va de
/// arriba-izquierda a abajo-derecha.
const atlasPanelGradient = LinearGradient(
  begin: Alignment.topLeft,
  end: Alignment.bottomRight,
  colors: [AtlasColors.panel2, AtlasColors.panel],
);

/// Decoración de `.card`: panel plano con borde, radio chico. Es la fila de
/// lista que usan dispositivos, rutinas, avisos y memoria — un solo lugar
/// para que las cuatro pantallas no diverjan.
BoxDecoration atlasCardDecoration({bool highlighted = false}) {
  return BoxDecoration(
    color: AtlasColors.panel,
    borderRadius: BorderRadius.circular(AtlasRadius.card),
    border: Border.all(color: highlighted ? AtlasColors.accentLine : AtlasColors.border),
  );
}

ThemeData buildAtlasTheme() {
  return ThemeData(
    useMaterial3: true,
    brightness: Brightness.dark,
    fontFamily: AtlasFonts.body,
    scaffoldBackgroundColor: AtlasColors.bg,
    colorScheme: const ColorScheme.dark(
      primary: AtlasColors.accent,
      onPrimary: AtlasColors.accentOn,
      surface: AtlasColors.panel,
      onSurface: AtlasColors.text,
      error: AtlasColors.danger,
    ),
    appBarTheme: const AppBarTheme(
      backgroundColor: AtlasColors.bg,
      foregroundColor: AtlasColors.text,
      elevation: 0,
    ),
    inputDecorationTheme: InputDecorationTheme(
      filled: true,
      fillColor: AtlasColors.panel,
      border: OutlineInputBorder(
        borderRadius: BorderRadius.circular(AtlasRadius.card),
        borderSide: const BorderSide(color: AtlasColors.borderBright),
      ),
      enabledBorder: OutlineInputBorder(
        borderRadius: BorderRadius.circular(AtlasRadius.card),
        borderSide: const BorderSide(color: AtlasColors.borderBright),
      ),
      focusedBorder: OutlineInputBorder(
        borderRadius: BorderRadius.circular(AtlasRadius.card),
        borderSide: const BorderSide(color: AtlasColors.accentLine),
      ),
      hintStyle: const TextStyle(color: AtlasColors.textFaint),
    ),
    elevatedButtonTheme: ElevatedButtonThemeData(
      style: ElevatedButton.styleFrom(
        backgroundColor: AtlasColors.accent,
        foregroundColor: AtlasColors.accentOn,
        padding: const EdgeInsets.symmetric(vertical: 14),
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(AtlasRadius.card)),
        textStyle: const TextStyle(fontFamily: AtlasFonts.body, fontWeight: FontWeight.w700),
      ),
    ),
    navigationBarTheme: NavigationBarThemeData(
      backgroundColor: AtlasColors.panel,
      indicatorColor: AtlasColors.accentSoft,
      labelTextStyle: WidgetStateProperty.all(
        const TextStyle(fontFamily: AtlasFonts.body, fontSize: 11, color: AtlasColors.textDim),
      ),
    ),
    dividerTheme: const DividerThemeData(color: AtlasColors.border, space: 1, thickness: 1),
    // Sin esto el SnackBar sale con el gris claro de Material por defecto y
    // desentona con todo lo demás (se ve en las confirmaciones de "Ejecutar").
    snackBarTheme: SnackBarThemeData(
      backgroundColor: AtlasColors.panel2,
      contentTextStyle: const TextStyle(fontFamily: AtlasFonts.body, color: AtlasColors.text, fontSize: 13.5),
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(AtlasRadius.card),
        side: const BorderSide(color: AtlasColors.borderBright),
      ),
      behavior: SnackBarBehavior.floating,
    ),
    textTheme: const TextTheme(
      bodyMedium: TextStyle(color: AtlasColors.text),
      bodySmall: TextStyle(color: AtlasColors.textDim),
    ),
  );
}
