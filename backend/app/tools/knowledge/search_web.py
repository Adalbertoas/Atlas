from __future__ import annotations

from app.integrations.web_search import WebSearchError, WebSearchNotConfigured, search_web
from app.security.permissions import RiskLevel
from app.tools.base import Tool, ToolContext, ToolResult


class SearchWebTool(Tool):
    name = "search_web"
    # La descripción es lo único que guía al modelo sobre CUÁNDO usar esto en
    # vez de responder de memoria o ir a Wikipedia. Es deliberadamente
    # explícita sobre los tres casos donde su propio conocimiento no alcanza.
    description = (
        "Busca en internet información actual. Usar cuando la respuesta depende de "
        "algo posterior a tu entrenamiento o que cambia con el tiempo: noticias, "
        "resultados deportivos, precios, cotizaciones, horarios de negocios, "
        "lanzamientos recientes, o cualquier cosa donde equivocarse por estar "
        "desactualizado sea un problema. Para temas enciclopédicos estables "
        "(historia, biografías, conceptos) preferí search_wikipedia. Si sabés la "
        "respuesta con certeza y no depende de la fecha, respondé directamente."
    )
    parameters = {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "Qué buscar, redactado como se buscaría en un buscador.",
            },
        },
        "required": ["query"],
    }
    risk_level = RiskLevel.READ_ONLY

    def __init__(self, provider: str = "duckduckgo", api_key: str = "") -> None:
        self._provider = provider
        self._api_key = api_key

    def execute(self, params: dict, context: ToolContext) -> ToolResult:
        query = (params.get("query") or "").strip()
        if not query:
            return ToolResult(success=False, error="Falta el parámetro 'query'.")

        try:
            response = search_web(query, provider=self._provider, api_key=self._api_key)
        except (WebSearchNotConfigured, WebSearchError) as exc:
            return ToolResult(success=False, error=str(exc))
        except Exception as exc:  # noqa: BLE001 — una búsqueda fallida no debe tumbar el turno
            return ToolResult(success=False, error=f"La búsqueda web falló: {exc}")

        return ToolResult(success=True, data=response.as_text())
