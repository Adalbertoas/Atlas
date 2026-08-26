"""analyze_screenshot: captura la pantalla de la PC y la describe (sección 16).

HIGH_RISK (igual que "acceder a una cámara" en la sección 5): una captura
de pantalla puede exponer información tan sensible como una cámara
(contraseñas visibles, conversaciones privadas), así que siempre pide
confirmación — nunca se ejecuta sola, ni siquiera disparada por una rutina
(ya blindado por execute_routine, Fase 6).
"""
from __future__ import annotations

import io

from PIL import ImageGrab

from app.security.permissions import RiskLevel
from app.tools.base import Tool, ToolContext, ToolResult
from app.vision.base import VisionProvider


class AnalyzeScreenshotTool(Tool):
    name = "analyze_screenshot"
    description = "Captura la pantalla actual de la PC y la describe (útil para diagnosticar errores en pantalla)."
    parameters = {
        "type": "object",
        "properties": {
            "question": {
                "type": "string",
                "description": "Qué preguntar sobre lo que se ve en pantalla. Opcional.",
            }
        },
        "required": [],
    }
    risk_level = RiskLevel.HIGH_RISK

    def __init__(self, provider: VisionProvider) -> None:
        self._provider = provider

    def human_description(self, params: dict) -> str:
        return "Capturar y analizar la pantalla actual"

    def execute(self, params: dict, context: ToolContext) -> ToolResult:
        try:
            screenshot = ImageGrab.grab()
        except Exception as exc:  # noqa: BLE001 — ej. sin entorno gráfico disponible
            return ToolResult(success=False, error=f"No pude capturar la pantalla: {exc}")

        buffer = io.BytesIO()
        screenshot.save(buffer, format="PNG")

        try:
            description = self._provider.analyze(buffer.getvalue(), params.get("question"))
        except Exception as exc:  # noqa: BLE001
            return ToolResult(success=False, error=str(exc))

        return ToolResult(success=True, data=description)
