"""Controlador de mouse por gestos (cámara del celular vía WebSocket).

No pasa por el Orchestrator/AI ni por el Permission Manager: es control
directo de bajo nivel, equivalente a un mouse físico — mismo criterio
acordado con el usuario para esta función. La detección de la mano (Media
Pipe Hands) corre en el navegador del celular; acá solo se reciben
coordenadas normalizadas (0-1) y un booleano de pellizco, nunca video.
"""
from __future__ import annotations

import pyautogui

pyautogui.FAILSAFE = True  # mover el mouse a una esquina de la pantalla aborta — protección estándar
pyautogui.MINIMUM_DURATION = 0
pyautogui.PAUSE = 0  # sin la pausa de 0.1s por defecto entre llamadas: necesitamos baja latencia

SMOOTHING_ALPHA = 0.35  # media móvil exponencial: 0 = sin movimiento, 1 = sin suavizado
SCROLL_SENSITIVITY = 4000  # multiplica el delta normalizado (0-1) antes de mandarlo a pyautogui.scroll


class MouseController:
    def __init__(self) -> None:
        self._screen_w, self._screen_h = pyautogui.size()
        self._smoothed_x: float | None = None
        self._smoothed_y: float | None = None
        self._is_down = False

    def _smooth(self, prev: float | None, new: float, alpha: float = SMOOTHING_ALPHA) -> float:
        if prev is None:
            return new
        return prev + alpha * (new - prev)

    def update(self, x_norm: float, y_norm: float, pinching: bool) -> None:
        """x_norm/y_norm: 0-1 relativo al frame de la cámara. pinching: si el
        usuario está pellizcando (pulgar+índice) en este frame."""
        x_norm = min(1.0, max(0.0, x_norm))
        y_norm = min(1.0, max(0.0, y_norm))

        self._smoothed_x = self._smooth(self._smoothed_x, x_norm)
        self._smoothed_y = self._smooth(self._smoothed_y, y_norm)

        screen_x = int(self._smoothed_x * self._screen_w)
        screen_y = int(self._smoothed_y * self._screen_h)
        pyautogui.moveTo(screen_x, screen_y)

        if pinching and not self._is_down:
            pyautogui.mouseDown()
            self._is_down = True
        elif not pinching and self._is_down:
            pyautogui.mouseUp()
            self._is_down = False

    def scroll(self, delta_norm: float) -> None:
        """delta_norm: movimiento vertical del gesto de dos dedos entre este
        frame y el anterior, en unidades normalizadas (positivo = mano subió
        = scroll hacia arriba). Lo calcula el celular, acá solo se escala."""
        clicks = int(delta_norm * SCROLL_SENSITIVITY)
        if clicks != 0:
            pyautogui.scroll(clicks)

    def release(self) -> None:
        """Se llama al desconectar/desactivar — evita dejar el botón del
        mouse apretado si la conexión se corta a mitad de un pellizco."""
        if self._is_down:
            pyautogui.mouseUp()
            self._is_down = False
