"""Paleta e identidad visual del cliente de escritorio (Fase 14).

Los mismos valores que dashboard/styles.css, para que los dos clientes de
PC se vean como el mismo producto. Acá viven como constantes de Python
porque Tkinter no tiene hojas de estilo ni variables CSS: cada widget
recibe sus colores a mano, y tenerlos en un solo lugar evita que se vayan
desincronizando.
"""
from __future__ import annotations

# --- Superficies ---
BG = "#060a10"
PANEL = "#0b1119"
PANEL_2 = "#0e1620"
SIDEBAR = "#080d14"
BORDER = "#16202c"
BORDER_BRIGHT = "#1d2b3a"
INPUT_BG = "#04090f"

# --- Texto ---
TEXT = "#e6edf5"
TEXT_DIM = "#7b8896"
TEXT_FAINT = "#55616e"

# --- Acento y estados ---
ACCENT = "#22d3ee"
ACCENT_DARK = "#0e7f92"
ACCENT_INK = "#04141a"  # texto sobre fondo de acento
OK = "#34d399"
WARN = "#fbbf24"
DANGER = "#f87171"
DANGER_INK = "#1a0505"

# Pista de los anillos de métricas: el "vacío" del anillo.
TRACK = "#1a2531"

# --- Tipografía ---
# Segoe UI está en cualquier Windows; el fallback lo resuelve Tk solo.
FONT_FAMILY = "Segoe UI"
FONT_TITLE = (FONT_FAMILY, 19, "bold")
FONT_SUBTITLE = (FONT_FAMILY, 10)
FONT_SECTION = (FONT_FAMILY, 9, "bold")  # encabezados de panel, en mayúsculas
FONT_BODY = (FONT_FAMILY, 12)
FONT_SMALL = (FONT_FAMILY, 10)
FONT_TINY = (FONT_FAMILY, 9)
FONT_METRIC = (FONT_FAMILY, 11, "bold")
FONT_BUTTON = (FONT_FAMILY, 11)

# --- Geometría ---
RADIUS = 12
RADIUS_SM = 9
