"""web_search / read_web_page: acceso a internet (app/web/client.py)."""
from __future__ import annotations

from app.security.permissions import RiskLevel
from app.tools.base import Tool, ToolContext, ToolResult
from app.web import client

DEFAULT_RESULTS = 5
MAX_RESULTS = 10
MAX_PAGE_CHARS = 6000  # el texto va al contexto del modelo: se acota


class WebSearchTool(Tool):
    name = "web_search"
    description = (
        "Busca en internet y devuelve títulos, links y resúmenes. Usala para noticias, datos "
        "actuales o cualquier cosa que no sepas. Para leer el contenido de un resultado usá read_web_page."
    )
    parameters = {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "Qué buscar."},
            "limit": {
                "type": "integer",
                "description": f"Cantidad de resultados (por defecto {DEFAULT_RESULTS}, tope {MAX_RESULTS}).",
            },
        },
        "required": ["query"],
    }
    risk_level = RiskLevel.READ_ONLY

    def __init__(self, brave_api_key: str = "") -> None:
        self._brave_api_key = brave_api_key

    def execute(self, params: dict, context: ToolContext) -> ToolResult:
        query = str(params.get("query", "")).strip()
        if not query:
            return ToolResult(success=False, error="El parámetro 'query' no puede estar vacío.")
        try:
            limit = max(1, min(int(params.get("limit") or DEFAULT_RESULTS), MAX_RESULTS))
        except (TypeError, ValueError):
            limit = DEFAULT_RESULTS
        try:
            results, source = client.search(query, limit, self._brave_api_key)
        except client.WebError as exc:
            return ToolResult(success=False, error=str(exc))
        if not results:
            return ToolResult(success=True, data=f"No encontré resultados para '{query}'.")
        lines = [f"Resultados de {source} para '{query}':"]
        if source == "Wikipedia":
            lines.append(
                "(Los buscadores generales no respondieron: solo hay artículos de Wikipedia, "
                "que no sirven para noticias ni datos del día.)"
            )
        lines += [f"{i}. {r.title} — {r.url}\n   {r.snippet}" for i, r in enumerate(results, 1)]
        return ToolResult(success=True, data="\n".join(lines))


class ReadWebPageTool(Tool):
    name = "read_web_page"
    description = "Abre una página web pública y devuelve su texto, para leerla o resumirla."
    parameters = {
        "type": "object",
        "properties": {"url": {"type": "string", "description": "Dirección de la página."}},
        "required": ["url"],
    }
    risk_level = RiskLevel.READ_ONLY

    def execute(self, params: dict, context: ToolContext) -> ToolResult:
        url = str(params.get("url", "")).strip()
        if not url:
            return ToolResult(success=False, error="El parámetro 'url' no puede estar vacío.")
        try:
            title, text = client.read_page(url)
        except client.WebError as exc:
            return ToolResult(success=False, error=str(exc))
        if not text.strip():
            return ToolResult(success=True, data=f"'{title}' no tiene texto legible (puede necesitar JavaScript).")
        if len(text) > MAX_PAGE_CHARS:
            text = text[:MAX_PAGE_CHARS] + "… (recortado)"
        return ToolResult(success=True, data=f"{title}\n\n{text}")
