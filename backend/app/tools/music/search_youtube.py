from __future__ import annotations

from app.integrations.youtube import search_youtube
from app.security.permissions import RiskLevel
from app.tools.base import Tool, ToolContext, ToolResult


class SearchYouTubeTool(Tool):
    name = "search_youtube"
    description = "Busca videos en YouTube y devuelve título, canal y link. No los reproduce ni descarga."
    parameters = {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "Qué buscar, ej. 'tutorial de python'."},
        },
        "required": ["query"],
    }
    risk_level = RiskLevel.READ_ONLY

    def __init__(self, api_key: str) -> None:
        self._api_key = api_key

    def execute(self, params: dict, context: ToolContext) -> ToolResult:
        query = params.get("query", "").strip()
        if not query:
            return ToolResult(success=False, error="Falta el parámetro 'query'.")

        try:
            videos = search_youtube(query, api_key=self._api_key)
        except Exception as exc:  # noqa: BLE001
            return ToolResult(success=False, error=str(exc))

        if not videos:
            return ToolResult(success=True, data=f"No encontré videos de YouTube para '{query}'.")

        summary = "; ".join(f"{v.title} — {v.channel} ({v.url})" for v in videos)
        return ToolResult(success=True, data=summary)
