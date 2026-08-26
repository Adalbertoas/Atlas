from __future__ import annotations

import os
from pathlib import Path

from app.security.permissions import RiskLevel
from app.tools.base import Tool, ToolContext, ToolResult

MAX_ENTRIES = 200


class ListFilesTool(Tool):
    name = "list_files"
    description = "Lista los archivos y carpetas dentro de un directorio."
    parameters = {
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "Ruta del directorio a listar. Por defecto, la carpeta de usuario actual.",
            }
        },
        "required": [],
    }
    risk_level = RiskLevel.READ_ONLY

    def execute(self, params: dict, context: ToolContext) -> ToolResult:
        raw_path = params.get("path") or str(Path.home())
        try:
            target = Path(raw_path).expanduser().resolve()
        except Exception as exc:  # noqa: BLE001
            return ToolResult(success=False, error=f"Ruta inválida: {exc}")

        if not target.exists() or not target.is_dir():
            return ToolResult(success=False, error=f"'{target}' no existe o no es un directorio.")

        try:
            entries = []
            with os.scandir(target) as it:
                for entry in it:
                    entries.append({"name": entry.name, "is_dir": entry.is_dir()})
                    if len(entries) >= MAX_ENTRIES:
                        break
            return ToolResult(success=True, data={"path": str(target), "entries": entries})
        except PermissionError:
            return ToolResult(success=False, error=f"Sin permiso para leer '{target}'.")
        except Exception as exc:  # noqa: BLE001
            return ToolResult(success=False, error=str(exc))
