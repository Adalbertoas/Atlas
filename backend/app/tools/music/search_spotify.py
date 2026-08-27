from __future__ import annotations

from app.integrations.spotify import SpotifyClient
from app.security.permissions import RiskLevel
from app.tools.base import Tool, ToolContext, ToolResult


class SearchSpotifyTool(Tool):
    name = "search_spotify"
    description = (
        "Busca una canción en Spotify y devuelve nombre, artista y link. "
        "Solo búsqueda: no controla la reproducción de nadie."
    )
    parameters = {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "Canción o artista a buscar."},
        },
        "required": ["query"],
    }
    risk_level = RiskLevel.READ_ONLY

    def __init__(self, client: SpotifyClient) -> None:
        self._client = client

    def execute(self, params: dict, context: ToolContext) -> ToolResult:
        query = params.get("query", "").strip()
        if not query:
            return ToolResult(success=False, error="Falta el parámetro 'query'.")

        try:
            tracks = self._client.search_track(query)
        except Exception as exc:  # noqa: BLE001
            return ToolResult(success=False, error=str(exc))

        if not tracks:
            return ToolResult(success=True, data=f"No encontré canciones en Spotify para '{query}'.")

        summary = "; ".join(f"{t.name} — {t.artists} ({t.url})" for t in tracks)
        return ToolResult(success=True, data=summary)
