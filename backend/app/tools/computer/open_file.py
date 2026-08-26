"""open_file: abre un archivo con la aplicación asociada de Windows.

Se bloquean extensiones ejecutables/script para no convertirse en una forma
indirecta de ejecución arbitraria (mismo espíritu que el allowlist de
open_application.py — sección 12: "No permitir ejecución arbitraria").
"""
from __future__ import annotations

import os
from pathlib import Path

from app.security.permissions import RiskLevel
from app.tools.base import Tool, ToolContext, ToolResult

BLOCKED_EXTENSIONS = {".exe", ".bat", ".cmd", ".ps1", ".vbs", ".msi", ".scr", ".com", ".js"}


class OpenFileTool(Tool):
    name = "open_file"
    description = "Abre un archivo (documento, imagen, etc.) con la aplicación asociada de Windows."
    parameters = {
        "type": "object",
        "properties": {"path": {"type": "string", "description": "Ruta completa del archivo a abrir."}},
        "required": ["path"],
    }
    risk_level = RiskLevel.MEDIUM_RISK

    def human_description(self, params: dict) -> str:
        return f"Abrir el archivo '{params.get('path', '?')}'"

    def execute(self, params: dict, context: ToolContext) -> ToolResult:
        raw_path = str(params.get("path", "")).strip()
        if not raw_path:
            return ToolResult(success=False, error="El parámetro 'path' no puede estar vacío.")

        try:
            target = Path(raw_path).expanduser().resolve()
        except Exception as exc:  # noqa: BLE001
            return ToolResult(success=False, error=f"Ruta inválida: {exc}")

        if not target.exists() or not target.is_file():
            return ToolResult(success=False, error=f"'{target}' no existe o no es un archivo.")

        if target.suffix.lower() in BLOCKED_EXTENSIONS:
            return ToolResult(
                success=False,
                error=f"No abro archivos '{target.suffix}' por seguridad (usa open_application para programas).",
            )

        try:
            os.startfile(target)  # noqa: S606 — ruta validada arriba, extensiones ejecutables ya bloqueadas
            return ToolResult(success=True, data=f"Archivo '{target}' abierto correctamente.")
        except OSError as exc:
            return ToolResult(success=False, error=str(exc))
