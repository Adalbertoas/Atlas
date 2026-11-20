"""Controlador de mouse por gestos (cámara del celular vía WebSocket).

No pasa por el Orchestrator/AI ni por el Permission Manager: es control
directo de bajo nivel, equivalente a un mouse físico — mismo criterio
acordado con el usuario para esta función. La detección de la mano (Media
Pipe Hands) corre en el navegador del celular; acá solo se reciben
coordenadas normalizadas (0-1) y un booleano de pellizco, nunca video.
"""
from __future__ import annotations

import ctypes

try:  # sin pantalla (servidor Linux) pyautogui ni siquiera se puede importar
    import pyautogui
except Exception:  # noqa: BLE001
    pyautogui = None
else:
    pyautogui.FAILSAFE = True  # mover el mouse a una esquina de la pantalla aborta — protección estándar
    pyautogui.MINIMUM_DURATION = 0
    pyautogui.PAUSE = 0  # sin la pausa de 0.1s por defecto entre llamadas: necesitamos baja latencia

SMOOTHING_ALPHA = 0.35  # media móvil exponencial: 0 = sin movimiento, 1 = sin suavizado
SCROLL_SENSITIVITY = 4000  # multiplica el delta normalizado (0-1) antes de mandarlo a pyautogui.scroll

# Valores de GetSystemMetrics para el escritorio virtual de Windows. A
# diferencia de pyautogui.size(), incluyen todas las pantallas y respetan que
# un monitor pueda estar a la izquierda o encima del principal (coordenadas
# negativas).
SM_XVIRTUALSCREEN = 76
SM_YVIRTUALSCREEN = 77
SM_CXVIRTUALSCREEN = 78
SM_CYVIRTUALSCREEN = 79


def _virtual_screen_bounds() -> tuple[int, int, int, int]:
    """Devuelve ``x, y, ancho, alto`` del escritorio virtual.

    El fallback mantiene la compatibilidad fuera de Windows y con entornos de
    prueba sin la API Win32.
    """
    try:
        user32 = ctypes.windll.user32
        x = user32.GetSystemMetrics(SM_XVIRTUALSCREEN)
        y = user32.GetSystemMetrics(SM_YVIRTUALSCREEN)
        width = user32.GetSystemMetrics(SM_CXVIRTUALSCREEN)
        height = user32.GetSystemMetrics(SM_CYVIRTUALSCREEN)
        if width > 0 and height > 0:
            return x, y, width, height
    except (AttributeError, OSError):
        pass

    width, height = pyautogui.size()
    return 0, 0, width, height


class MouseController:
    def __init__(self) -> None:
        self._screen_x, self._screen_y, self._screen_w, self._screen_h = _virtual_screen_bounds()
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

        # ``-1`` evita generar una coordenada fuera del borde cuando la mano
        # llega exactamente a 1.0. Los offsets permiten abarcar el monitor
        # secundario aunque Windows lo haya colocado en X/Y negativo.
        screen_x = self._screen_x + int(self._smoothed_x * max(0, self._screen_w - 1))
        screen_y = self._screen_y + int(self._smoothed_y * max(0, self._screen_h - 1))
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
