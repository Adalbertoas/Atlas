"""Widgets dibujados a mano para el cliente de escritorio (Fase 14).

CustomTkinter no trae anillos de progreso ni visualizadores, y Tkinter no
tiene nada equivalente a un conic-gradient de CSS (que es como lo resuelve
el dashboard). Se dibujan sobre un Canvas.
"""
from __future__ import annotations

import math

import customtkinter as ctk

from atlas_desktop import theme


class MetricRing(ctk.CTkFrame):
    """Anillo de porcentaje con la etiqueta debajo (CPU / RAM / Disco).

    Equivalente al `.ring` del dashboard, que allá es un conic-gradient.
    """

    def __init__(self, master, label: str, size: int = 62, thickness: int = 5) -> None:
        super().__init__(master, fg_color="transparent")
        self._size = size
        self._thickness = thickness

        self._canvas = ctk.CTkCanvas(
            self, width=size, height=size, bg=theme.PANEL, highlightthickness=0, bd=0
        )
        self._canvas.pack()

        self._label = ctk.CTkLabel(
            self, text=label, font=theme.FONT_TINY, text_color=theme.TEXT_FAINT
        )
        self._label.pack(pady=(3, 0))

        self.set(None)

    def set(self, percent: float | None) -> None:
        """percent=None dibuja el anillo vacío con '--' (todavía sin datos)."""
        canvas = self._canvas
        canvas.delete("all")

        pad = self._thickness / 2 + 1
        box = (pad, pad, self._size - pad, self._size - pad)

        # Pista completa.
        canvas.create_oval(*box, outline=theme.TRACK, width=self._thickness)

        if percent is None:
            text = "--"
        else:
            value = max(0.0, min(100.0, float(percent)))
            text = f"{round(value)}%"
            if value > 0:
                # Tk mide en grados y en sentido antihorario: -extent para que
                # avance como un reloj, arrancando arriba (90°).
                canvas.create_arc(
                    *box,
                    start=90,
                    extent=-value * 3.6,
                    style="arc",
                    outline=theme.ACCENT,
                    width=self._thickness,
                )

        canvas.create_text(
            self._size / 2,
            self._size / 2,
            text=text,
            fill=theme.TEXT,
            font=theme.FONT_METRIC,
        )


class VoiceOrb(ctk.CTkFrame):
    """Orbe de voz: anillos concéntricos fijos y una onda que responde al
    nivel real del micrófono.

    Mismo criterio que el dashboard: **nada de animación decorativa**. En
    reposo el orbe está quieto; solo se mueve cuando hay audio real, y la
    amplitud sale de muestras del micrófono, no de un temporizador.
    """

    RINGS = (0.96, 0.80, 0.64, 0.46)  # radios como fracción del radio máximo

    def __init__(self, master, size: int = 150, bg: str = theme.BG) -> None:
        super().__init__(master, fg_color="transparent")
        self._size = size
        self._bg = bg
        self._level = 0.0  # 0..1, último nivel real recibido
        self._phase = 0.0  # avanza solo mientras hay señal, para que la onda fluya
        self._animating = False

        # `bg` configurable: un Canvas de Tk no puede ser transparente, así
        # que tiene que recibir exactamente el color del contenedor o se ve
        # un cuadrado de otro tono alrededor del dibujo.
        self._canvas = ctk.CTkCanvas(
            self, width=size, height=size, bg=bg, highlightthickness=0, bd=0
        )
        self._canvas.pack()
        self._render()

    # ---------- API pública ----------

    def set_level(self, level: float) -> None:
        """level: 0..1 — amplitud real del audio en este instante."""
        self._level = max(0.0, min(1.0, level))

    def start(self) -> None:
        if self._animating:
            return
        self._animating = True
        self._tick()

    def stop(self) -> None:
        self._animating = False
        self._level = 0.0
        self._phase = 0.0
        self._render()

    # ---------- interno ----------

    def _tick(self) -> None:
        if not self._animating:
            return
        # La fase avanza en proporción al nivel: sin señal, la onda queda
        # quieta en vez de girar sola simulando actividad.
        self._phase += 0.25 * self._level
        self._render()
        self.after(40, self._tick)

    def _render(self) -> None:
        canvas = self._canvas
        canvas.delete("all")

        center = self._size / 2
        max_radius = self._size / 2 - 4

        # Anillos concéntricos: marco fijo, no representan datos.
        for i, fraction in enumerate(self.RINGS):
            radius = max_radius * fraction
            canvas.create_oval(
                center - radius, center - radius, center + radius, center + radius,
                outline=_blend(self._bg, theme.ACCENT, 0.10 + i * 0.07),
                width=1,
            )

        # Onda: círculo deformado por el nivel real. Sin señal queda un
        # círculo perfecto, que es la verdad (no hay audio).
        base = max_radius * 0.52
        amplitude = max_radius * 0.30 * self._level
        points = []
        steps = 72
        for i in range(steps):
            angle = (i / steps) * math.tau
            wobble = math.sin(angle * 3 + self._phase) * amplitude
            radius = base + wobble
            points.append(center + math.cos(angle) * radius)
            points.append(center + math.sin(angle) * radius)

        canvas.create_polygon(
            points,
            outline=theme.ACCENT,
            fill=_blend(self._bg, theme.ACCENT, 0.10),
            width=2,
            smooth=True,
        )

        # Marca de ATLAS: triángulo, igual que el logo del dashboard.
        mark = max_radius * 0.20
        canvas.create_polygon(
            center, center - mark,
            center + mark * 0.88, center + mark * 0.62,
            center - mark * 0.88, center + mark * 0.62,
            outline=theme.ACCENT, fill="", width=2, joinstyle="round",
        )


class LevelBar(ctk.CTkFrame):
    """Barra horizontal de nivel de audio para la fila inferior. Igual que el
    orbe: se mueve solo con señal real."""

    def __init__(self, master, width: int = 260, height: int = 26, bg: str = theme.BG) -> None:
        super().__init__(master, fg_color="transparent")
        self._width = width
        self._height = height
        self._levels = [0.0] * 48  # historial corto, para que se lea como onda

        # `bg` configurable: el Canvas de Tk no admite fondo transparente,
        # así que si no coincide con el del contenedor se ve un rectángulo
        # de otro tono alrededor de la onda.
        self._canvas = ctk.CTkCanvas(
            self, width=width, height=height, bg=bg, highlightthickness=0, bd=0
        )
        self._canvas.pack()
        self._render()

    def push(self, level: float) -> None:
        self._levels.append(max(0.0, min(1.0, level)))
        self._levels.pop(0)
        self._render()

    def reset(self) -> None:
        self._levels = [0.0] * len(self._levels)
        self._render()

    def _render(self) -> None:
        canvas = self._canvas
        canvas.delete("all")
        mid = self._height / 2
        step = self._width / (len(self._levels) - 1)

        # Línea de base: en reposo se ve una línea plana, no una onda falsa.
        canvas.create_line(0, mid, self._width, mid, fill=theme.TRACK, width=1)

        for i, level in enumerate(self._levels):
            if level <= 0.02:
                continue
            x = i * step
            half = (self._height / 2 - 2) * level
            canvas.create_line(x, mid - half, x, mid + half, fill=theme.ACCENT, width=2)


class Panel(ctk.CTkFrame):
    """Tarjeta con borde y encabezado en mayúsculas — el `.panel` del
    dashboard. `body` es el contenedor donde va el contenido."""

    def __init__(self, master, title: str | None = None, action: tuple[str, object] | None = None):
        super().__init__(
            master, fg_color=theme.PANEL, corner_radius=theme.RADIUS,
            border_width=1, border_color=theme.BORDER,
        )
        self.grid_columnconfigure(0, weight=1)

        row = 0
        if title:
            head = ctk.CTkFrame(self, fg_color="transparent")
            head.grid(row=0, column=0, sticky="ew", padx=16, pady=(13, 9))
            head.grid_columnconfigure(0, weight=1)
            ctk.CTkLabel(
                head, text=title.upper(), font=theme.FONT_SECTION,
                text_color=theme.TEXT_DIM, anchor="w",
            ).grid(row=0, column=0, sticky="w")
            if action:
                label, command = action
                ctk.CTkButton(
                    head, text=label, width=1, height=18,
                    font=theme.FONT_TINY, corner_radius=6,
                    fg_color="transparent", hover_color=theme.PANEL_2,
                    text_color=theme.ACCENT, command=command,
                ).grid(row=0, column=1, sticky="e")
            row = 1

        self.body = ctk.CTkFrame(self, fg_color="transparent")
        self.body.grid(row=row, column=0, sticky="nsew", padx=12, pady=(0, 12))
        self.body.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(row, weight=1)


class Toggle(ctk.CTkButton):
    """Interruptor tipo píldora. CustomTkinter trae CTkSwitch, pero su
    apariencia no es configurable lo suficiente como para igualar el del
    dashboard, así que se compone con un botón redondeado."""

    def __init__(self, master, on: bool, command=None, enabled: bool = True):
        super().__init__(
            master, text="", width=38, height=21, corner_radius=11,
            border_width=1, command=command,
        )
        self.set_state(on, enabled)

    def set_state(self, on: bool, enabled: bool = True) -> None:
        self.configure(
            fg_color=theme.ACCENT if on else theme.TRACK,
            hover_color=theme.ACCENT_DARK if on else theme.BORDER_BRIGHT,
            border_color=theme.ACCENT if on else theme.BORDER_BRIGHT,
            state="normal" if enabled else "disabled",
        )


class MiniRow(ctk.CTkFrame):
    """Fila compacta de los paneles: título, subtítulo y un control o estado
    a la derecha. Equivale al `.mini-row` del dashboard."""

    def __init__(self, master, title: str, subtitle: str = "", accent: str | None = None):
        super().__init__(
            master, fg_color=theme.PANEL_2, corner_radius=theme.RADIUS_SM,
            border_width=1, border_color=theme.BORDER,
        )
        self.grid_columnconfigure(1, weight=1)

        # Barra de color a la izquierda: sustituye a los iconos SVG del
        # dashboard, que en Tkinter habría que dibujar uno por uno.
        #
        # height explícito: un CTkFrame sin hijos conserva su alto por
        # defecto (200 px) y estiraba cada fila a ese tamaño. Con hijos
        # propaga y se ajusta solo, pero esta barra está vacía a propósito.
        stripe = ctk.CTkFrame(
            self, width=3, height=26, corner_radius=2, fg_color=accent or theme.BORDER_BRIGHT
        )
        stripe.grid(row=0, column=0, rowspan=2, sticky="ns", padx=(9, 10), pady=9)

        ctk.CTkLabel(
            self, text=title, font=theme.FONT_SMALL, text_color=theme.TEXT, anchor="w",
        ).grid(row=0, column=1, sticky="ew", pady=(8, 0))

        if subtitle:
            ctk.CTkLabel(
                self, text=subtitle, font=theme.FONT_TINY, text_color=theme.TEXT_FAINT, anchor="w",
            ).grid(row=1, column=1, sticky="ew", pady=(0, 8))

        self.trailing = ctk.CTkFrame(self, fg_color="transparent")
        self.trailing.grid(row=0, column=2, rowspan=2, padx=(8, 10))


def empty_state(master, text: str) -> ctk.CTkLabel:
    """Mensaje de lista vacía, con el mismo tono apagado del dashboard."""
    return ctk.CTkLabel(
        master, text=text, font=theme.FONT_SMALL, text_color=theme.TEXT_FAINT,
        wraplength=320, justify="center",
    )


def clear(container) -> None:
    """Vacía un contenedor antes de repintarlo. Tkinter no tiene innerHTML:
    hay que destruir los hijos a mano o se van apilando en cada refresco."""
    for child in container.winfo_children():
        child.destroy()


def _blend(background: str, foreground: str, alpha: float) -> str:
    """Mezcla dos colores hex. Tkinter no soporta canales alfa: los tonos
    translúcidos del dashboard (rgba) hay que precalcularlos acá."""
    bg = _to_rgb(background)
    fg = _to_rgb(foreground)
    mixed = tuple(round(b + (f - b) * alpha) for b, f in zip(bg, fg))
    return "#%02x%02x%02x" % mixed


def _to_rgb(value: str) -> tuple[int, int, int]:
    value = value.lstrip("#")
    return int(value[0:2], 16), int(value[2:4], 16), int(value[4:6], 16)
