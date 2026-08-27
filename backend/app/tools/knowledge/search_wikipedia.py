from __future__ import annotations

from app.integrations.wikipedia import search_wikipedia
from app.security.permissions import RiskLevel
from app.tools.base import Tool, ToolContext, ToolResult


class SearchWikipediaTool(Tool):
    name = "search_wikipedia"
    description = (
        "Busca un tema en Wikipedia y devuelve un resumen. Usar cuando el usuario "
        "pregunta algo enciclopédico/factual que ATLAS no sabe de memoria con certeza."
    )
    parameters = {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "Tema a buscar, ej. 'Torre Eiffel'."},
        },
        "required": ["query"],
    }
    risk_level = RiskLevel.READ_ONLY

    def execute(self, params: dict, context: ToolContext) -> ToolResult:
        query = params.get("query", "").strip()
        if not query:
            return ToolResult(success=False, error="Falta el parámetro 'query'.")

        try:
            result = search_wikipedia(query)
        except Exception as exc:  # noqa: BLE001
            return ToolResult(success=False, error=f"No se pudo consultar Wikipedia: {exc}")

        if result is None:
            return ToolResult(success=True, data=f"No encontré ningún artículo de Wikipedia sobre '{query}'.")

        return ToolResult(success=True, data=f"{result.title}: {result.summary} ({result.url})")
