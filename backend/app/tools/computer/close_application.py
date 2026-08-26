"""close_application: cierra procesos por nombre (sección 12)."""
from __future__ import annotations

import psutil

from app.security.permissions import RiskLevel
from app.tools.base import Tool, ToolContext, ToolResult

TERMINATE_TIMEOUT_SECONDS = 3

# Alias -> nombre real del proceso, para los casos donde no coincide con el
# alias "de conversación" (ej. la Calculadora de Windows corre como
# "CalculatorApp.exe", no "calculadora.exe" ni "calc.exe" — el segundo es
# solo un stub que la lanza). Sin esto, "cierra la calculadora" nunca
# encontraría el proceso a pesar de estar corriendo.
PROCESS_NAME_ALIASES: dict[str, str] = {
    "calculadora": "calculatorapp",
    "calculator": "calculatorapp",
}


class CloseApplicationTool(Tool):
    name = "close_application"
    description = "Cierra una aplicación en ejecución, buscándola por nombre de proceso (ej. 'notepad', 'chrome')."
    parameters = {
        "type": "object",
        "properties": {
            "process_name": {
                "type": "string",
                "description": "Nombre (o parte del nombre) del proceso a cerrar, ej. 'notepad' o 'chrome'.",
            }
        },
        "required": ["process_name"],
    }
    risk_level = RiskLevel.MEDIUM_RISK  # cerrar puede perder trabajo no guardado: requiere confirmación

    def human_description(self, params: dict) -> str:
        name = params.get("process_name", "?")
        return f"Cerrar la aplicación '{name}'"

    def execute(self, params: dict, context: ToolContext) -> ToolResult:
        query = str(params.get("process_name", "")).strip().lower()
        if not query:
            return ToolResult(success=False, error="El parámetro 'process_name' no puede estar vacío.")
        query = PROCESS_NAME_ALIASES.get(query, query)

        matches = [
            p
            for p in psutil.process_iter(["pid", "name"])
            if query in (p.info["name"] or "").lower()
        ]
        if not matches:
            return ToolResult(success=False, error=f"No encontré ningún proceso corriendo llamado '{query}'.")

        closed, failed = [], []
        for proc in matches:
            try:
                proc.terminate()
            except (psutil.NoSuchProcess, psutil.AccessDenied) as exc:
                failed.append(f"{proc.info['name']} ({exc.__class__.__name__})")
                continue

        gone, alive = psutil.wait_procs(matches, timeout=TERMINATE_TIMEOUT_SECONDS)
        closed = [p.info.get("name", "?") for p in gone]
        for proc in alive:  # no cerraron a tiempo: forzar
            try:
                proc.kill()
                closed.append(proc.info.get("name", "?"))
            except (psutil.NoSuchProcess, psutil.AccessDenied) as exc:
                failed.append(f"{proc.info.get('name', '?')} ({exc.__class__.__name__})")

        if not closed:
            return ToolResult(success=False, error=f"No pude cerrar '{query}': {', '.join(failed) or 'error desconocido'}.")

        summary = f"Cerrado: {', '.join(closed)}."
        if failed:
            summary += f" No se pudo cerrar: {', '.join(failed)}."
        return ToolResult(success=True, data=summary)
