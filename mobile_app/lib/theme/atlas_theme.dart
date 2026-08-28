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
}

ThemeData buildAtlasTheme() {
  return ThemeData(
    useMaterial3: true,
    brightness: Brightness.dark,
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
        borderRadius: BorderRadius.circular(10),
        borderSide: const BorderSide(color: AtlasColors.borderBright),
      ),
      enabledBorder: OutlineInputBorder(
        borderRadius: BorderRadius.circular(10),
        borderSide: const BorderSide(color: AtlasColors.borderBright),
      ),
      focusedBorder: OutlineInputBorder(
        borderRadius: BorderRadius.circular(10),
        borderSide: const BorderSide(color: AtlasColors.accent),
      ),
      hintStyle: const TextStyle(color: AtlasColors.textFaint),
    ),
    elevatedButtonTheme: ElevatedButtonThemeData(
      style: ElevatedButton.styleFrom(
        backgroundColor: AtlasColors.accent,
        foregroundColor: AtlasColors.accentOn,
        padding: const EdgeInsets.symmetric(vertical: 14),
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(10)),
        textStyle: const TextStyle(fontWeight: FontWeight.w600),
      ),
    ),
    navigationBarTheme: NavigationBarThemeData(
      backgroundColor: AtlasColors.panel,
      indicatorColor: AtlasColors.accent.withValues(alpha: 0.16),
      labelTextStyle: WidgetStateProperty.all(
        const TextStyle(fontSize: 12, color: AtlasColors.textDim),
      ),
    ),
    textTheme: const TextTheme(
      bodyMedium: TextStyle(color: AtlasColors.text),
      bodySmall: TextStyle(color: AtlasColors.textDim),
    ),
  );
}
