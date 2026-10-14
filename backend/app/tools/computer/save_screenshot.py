"""save_screenshot: guarda una captura de pantalla como archivo PNG.

Distinto de analyze_screenshot (Fase 8), que le manda la pantalla a la IA
para describirla: esta solo la guarda en disco y no sale de la PC.
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path

from app.security.permissions import RiskLevel
from app.tools.base import Tool, ToolContext, ToolResult

SCREENSHOT_DIR = Path.home() / "Pictures" / "ATLAS"


class SaveScreenshotTool(Tool):
    name = "save_screenshot"
    description = (
        "Saca una captura de pantalla y la guarda como PNG en Imágenes/ATLAS. Usala cuando el usuario "
        "pida guardar una captura; para que ATLAS mire la pantalla y la describa usá analyze_screenshot."
    )
    parameters = {"type": "object", "properties": {}, "required": []}
    risk_level = RiskLevel.LOW_RISK  # crea un archivo nuevo en una carpeta propia; no pisa nada

    def __init__(self, directory: Path = SCREENSHOT_DIR) -> None:
        self._directory = directory

    def execute(self, params: dict, context: ToolContext) -> ToolResult:
        try:
            from PIL import ImageGrab  # import perezoso: solo hace falta al capturar

            image = ImageGrab.grab(all_screens=True)
            self._directory.mkdir(parents=True, exist_ok=True)
            path = self._directory / f"captura-{datetime.now():%Y%m%d-%H%M%S}.png"
            image.save(path, "PNG")
        except Exception as exc:  # noqa: BLE001
            return ToolResult(success=False, error=f"No pude capturar la pantalla: {exc}")
        return ToolResult(success=True, data=f"Captura guardada en {path} ({image.width}x{image.height}).")
