"""open_application: abre una aplicación conocida en Windows.

Regla de la sección 12 del prompt maestro: NO permitir ejecución arbitraria
de comandos. En vez de aceptar una ruta de ejecutable libre, se usa un
allowlist explícito de alias -> comando conocido. Cualquier alias fuera de
esta lista se rechaza.
"""
from __future__ import annotations

import shutil
import subprocess

from app.security.permissions import RiskLevel
from app.tools.base import Tool, ToolContext, ToolResult

# Allowlist de aplicaciones que ATLAS puede abrir. Se puede extender, pero
# siempre debe ser una lista explícita y curada, nunca una ruta arbitraria
# provista por el usuario o por la IA.
APPLICATION_ALLOWLIST: dict[str, list[str]] = {
    "vscode": ["code"],
    "vs code": ["code"],
    "notepad": ["notepad.exe"],
    "bloc de notas": ["notepad.exe"],
    "chrome": ["chrome"],
    "explorer": ["explorer.exe"],
    "explorador de archivos": ["explorer.exe"],
    "calculadora": ["calc.exe"],
    "calculator": ["calc.exe"],
}


class OpenApplicationTool(Tool):
    name = "open_application"
    description = (
        "Abre una aplicación conocida en el equipo (ej: vscode, notepad, chrome, "
        "calculadora, explorador de archivos). Solo funciona con aplicaciones de "
        "una lista permitida."
    )
    parameters = {
        "type": "object",
        "properties": {
            "application_name": {
                "type": "string",
                "description": f"Alias de la app a abrir. Opciones: {', '.join(sorted(set(APPLICATION_ALLOWLIST)))}",
            }
        },
        "required": ["application_name"],
    }
    risk_level = RiskLevel.MEDIUM_RISK  # requiere confirmación (sección 12: permiso computer.execute)

    def human_description(self, params: dict) -> str:
        app = params.get("application_name", "?")
        return f"Abrir la aplicación '{app}'"

    def execute(self, params: dict, context: ToolContext) -> ToolResult:
        app_name = str(params.get("application_name", "")).strip().lower()
        command = APPLICATION_ALLOWLIST.get(app_name)
        if command is None:
            return ToolResult(
                success=False,
                error=(
                    f"'{app_name}' no está en la lista de aplicaciones permitidas. "
                    f"Opciones válidas: {', '.join(sorted(set(APPLICATION_ALLOWLIST)))}"
                ),
            )

        executable = command[0]
        if shutil.which(executable) is None and not executable.lower().endswith(".exe"):
            return ToolResult(success=False, error=f"No se encontró el ejecutable '{executable}' en el PATH.")

        try:
            subprocess.Popen(command, shell=False)  # noqa: S603 — command viene de allowlist fijo, no de input libre
            return ToolResult(success=True, data=f"Aplicación '{app_name}' abierta correctamente.")
        except FileNotFoundError:
            return ToolResult(success=False, error=f"No se pudo encontrar/ejecutar '{executable}'.")
        except Exception as exc:  # noqa: BLE001
            return ToolResult(success=False, error=str(exc))
