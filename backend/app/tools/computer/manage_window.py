"""manage_window: acomodar ventanas de Windows (mitades de pantalla, maximizar, minimizar).

Win32 vía ctypes, sin dependencias nuevas. La ventana se elige por una parte
de su título; sin título se usa la que está en primer plano.
"""
from __future__ import annotations

import ctypes
from ctypes import wintypes

from app.security.permissions import RiskLevel
from app.tools.base import Tool, ToolContext, ToolResult

SW_MAXIMIZE = 3
SW_MINIMIZE = 6
SW_RESTORE = 9
SPI_GETWORKAREA = 0x0030
SWP_NOZORDER = 0x0004
SWP_SHOWWINDOW = 0x0040

ACTIONS = ["left", "right", "maximize", "minimize", "restore", "focus"]


def _user32():
    user32 = ctypes.WinDLL("user32", use_last_error=True)
    user32.GetForegroundWindow.restype = wintypes.HWND
    user32.GetWindowTextLengthW.argtypes = [wintypes.HWND]
    user32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
    user32.IsWindowVisible.argtypes = [wintypes.HWND]
    user32.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]
    user32.SetForegroundWindow.argtypes = [wintypes.HWND]
    user32.SetWindowPos.argtypes = [
        wintypes.HWND, wintypes.HWND, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, wintypes.UINT,
    ]  # fmt: skip
    return user32


def _title(user32, hwnd) -> str:
    length = user32.GetWindowTextLengthW(hwnd)
    if length <= 0:
        return ""
    buffer = ctypes.create_unicode_buffer(length + 1)
    user32.GetWindowTextW(hwnd, buffer, length + 1)
    return buffer.value


def list_windows() -> list[tuple[int, str]]:
    """(handle, título) de las ventanas visibles con título."""
    user32 = _user32()
    found: list[tuple[int, str]] = []
    callback_type = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

    def collect(hwnd, _lparam) -> bool:
        if user32.IsWindowVisible(hwnd):
            title = _title(user32, hwnd)
            if title:
                found.append((hwnd, title))
        return True

    user32.EnumWindows(callback_type(collect), 0)
    return found


def _work_area(user32) -> tuple[int, int, int, int]:
    """Área útil del monitor principal (sin la barra de tareas): left, top, width, height."""
    rect = wintypes.RECT()
    user32.SystemParametersInfoW(SPI_GETWORKAREA, 0, ctypes.byref(rect), 0)
    return rect.left, rect.top, rect.right - rect.left, rect.bottom - rect.top


class ManageWindowTool(Tool):
    name = "manage_window"
    description = (
        "Acomoda una ventana de Windows: left/right la ponen en la mitad izquierda/derecha de la "
        "pantalla, maximize, minimize, restore, o focus para traerla al frente. La ventana se elige "
        "por parte de su título (ej. 'Chrome', 'Bloc de notas'); sin título, la que está en primer plano."
    )
    parameters = {
        "type": "object",
        "properties": {
            "action": {"type": "string", "enum": ACTIONS, "description": "Qué hacer con la ventana."},
            "window": {"type": "string", "description": "Parte del título de la ventana."},
        },
        "required": ["action"],
    }
    risk_level = RiskLevel.LOW_RISK  # reversible y no destructivo: se ejecuta directo

    def execute(self, params: dict, context: ToolContext) -> ToolResult:
        action = str(params.get("action", "")).strip().lower()
        if action not in ACTIONS:
            return ToolResult(success=False, error=f"Acción '{action}' no reconocida. Opciones: {', '.join(ACTIONS)}")
        query = str(params.get("window") or "").strip().lower()

        try:
            user32 = _user32()
            if query:
                matches = [(h, t) for h, t in list_windows() if query in t.lower()]
                if not matches:
                    titles = "; ".join(t for _, t in list_windows()[:12])
                    return ToolResult(
                        success=False, error=f"No encontré una ventana con '{query}'. Abiertas: {titles}"
                    )
                hwnd, title = matches[0]
            else:
                hwnd = user32.GetForegroundWindow()
                if not hwnd:
                    return ToolResult(success=False, error="No hay ninguna ventana en primer plano.")
                title = _title(user32, hwnd) or "la ventana activa"

            if action == "maximize":
                user32.ShowWindow(hwnd, SW_MAXIMIZE)
            elif action == "minimize":
                user32.ShowWindow(hwnd, SW_MINIMIZE)
            elif action == "restore":
                user32.ShowWindow(hwnd, SW_RESTORE)
            elif action == "focus":
                user32.ShowWindow(hwnd, SW_RESTORE)
                user32.SetForegroundWindow(hwnd)
            else:
                left, top, width, height = _work_area(user32)
                half = width // 2
                x = left if action == "left" else left + half
                user32.ShowWindow(hwnd, SW_RESTORE)  # una ventana maximizada ignora SetWindowPos
                user32.SetWindowPos(hwnd, None, x, top, half, height, SWP_NOZORDER | SWP_SHOWWINDOW)
        except Exception as exc:  # noqa: BLE001
            return ToolResult(success=False, error=str(exc))

        return ToolResult(success=True, data=f"Listo: '{action}' aplicado a «{title}».")
