"""control_media: play/pause, siguiente/anterior pista, volumen (sección 12).

Se simulan las teclas multimedia de Windows vía ctypes (user32.keybd_event) —
funciona con cualquier reproductor que responda a esas teclas (Spotify,
YouTube, reproductor por defecto de Windows, etc.), sin dependencias nuevas.
"""
from __future__ import annotations

import ctypes

from app.security.permissions import RiskLevel
from app.tools.base import Tool, ToolContext, ToolResult

KEYEVENTF_EXTENDEDKEY = 0x1
KEYEVENTF_KEYUP = 0x2

# Virtual-key codes de teclas multimedia de Windows.
_ACTION_VK = {
    "play_pause": 0xB3,
    "next": 0xB0,
    "previous": 0xB1,
    "volume_up": 0xAF,
    "volume_down": 0xAE,
    "mute": 0xAD,
}


def _press_media_key(vk_code: int) -> None:
    ctypes.windll.user32.keybd_event(vk_code, 0, KEYEVENTF_EXTENDEDKEY, 0)
    ctypes.windll.user32.keybd_event(vk_code, 0, KEYEVENTF_EXTENDEDKEY | KEYEVENTF_KEYUP, 0)


class ControlMediaTool(Tool):
    name = "control_media"
    description = "Controla la reproducción multimedia: play/pausa, siguiente, anterior, volumen, silenciar."
    parameters = {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "description": f"Una de: {', '.join(_ACTION_VK)}",
            }
        },
        "required": ["action"],
    }
    risk_level = RiskLevel.LOW_RISK  # reversible y no destructivo: se ejecuta directo

    def execute(self, params: dict, context: ToolContext) -> ToolResult:
        action = str(params.get("action", "")).strip().lower()
        vk_code = _ACTION_VK.get(action)
        if vk_code is None:
            return ToolResult(
                success=False,
                error=f"Acción '{action}' no reconocida. Opciones: {', '.join(_ACTION_VK)}",
            )
        try:
            _press_media_key(vk_code)
            return ToolResult(success=True, data=f"Acción de multimedia '{action}' ejecutada.")
        except Exception as exc:  # noqa: BLE001
            return ToolResult(success=False, error=str(exc))
