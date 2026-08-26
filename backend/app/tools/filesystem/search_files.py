from __future__ import annotations

from pathlib import Path

from app.security.permissions import RiskLevel
from app.tools.base import Tool, ToolContext, ToolResult

MAX_RESULTS = 100
MAX_SCAN = 20_000  # límite de archivos inspeccionados, para no colgar el proceso


class SearchFilesTool(Tool):
    name = "search_files"
    description = "Busca archivos por nombre (coincidencia parcial) dentro de un directorio."
    parameters = {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "Texto a buscar en el nombre del archivo."},
            "path": {
                "type": "string",
                "description": "Directorio base de la búsqueda. Por defecto, la carpeta de usuario.",
            },
        },
        "required": ["query"],
    }
    risk_level = RiskLevel.READ_ONLY

    def execute(self, params: dict, context: ToolContext) -> ToolResult:
        query = str(params.get("query", "")).strip().lower()
        if not query:
            return ToolResult(success=False, error="El parámetro 'query' no puede estar vacío.")

        raw_path = params.get("path") or str(Path.home())
        try:
            base = Path(raw_path).expanduser().resolve()
        except Exception as exc:  # noqa: BLE001
            return ToolResult(success=False, error=f"Ruta inválida: {exc}")

        if not base.exists() or not base.is_dir():
            return ToolResult(success=False, error=f"'{base}' no existe o no es un directorio.")

        matches: list[str] = []
        scanned = 0
        try:
            for item in base.rglob("*"):
                scanned += 1
                if scanned > MAX_SCAN:
                    break
                if query in item.name.lower():
                    matches.append(str(item))
                    if len(matches) >= MAX_RESULTS:
                        break
        except PermissionError:
            pass  # ignoramos subcarpetas sin permiso, seguimos con lo encontrado hasta ahora

        return ToolResult(success=True, data={"query": query, "base": str(base), "matches": matches})
