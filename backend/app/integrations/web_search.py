"""Búsqueda web (Fase 19) — el hueco más grande que le quedaba a ATLAS.

Wikipedia solo cubre temas enciclopédicos, y el conocimiento del modelo se
corta en su fecha de entrenamiento. Sin esto, ATLAS no podía responder nada
actual: noticias, precios, si un negocio está abierto, qué pasó ayer.

Dos proveedores, mismo criterio que smart_home y voz — uno sin configurar
nada y otro mejor pero con cuenta:

  · **duckduckgo** (por defecto): sin API key, sin registro, funciona al
    instante. Usa la librería `ddgs`, que raspa DuckDuckGo por una vía no
    oficial: puede limitar por frecuencia o romperse sin aviso.
  · **tavily**: pensada para agentes de IA — devuelve además una respuesta
    ya sintetizada, no solo enlaces. 1.000 consultas/mes gratis con cuenta.

Brave quedó afuera a propósito: retiró su plan gratuito a fines de 2025.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass

import requests

logger = logging.getLogger(__name__)

_TIMEOUT = 15


class WebSearchNotConfigured(Exception):
    """Falta la API key del proveedor elegido."""


class WebSearchError(Exception):
    """El proveedor falló o no está disponible."""


@dataclass
class SearchResult:
    title: str
    snippet: str
    url: str


@dataclass
class SearchResponse:
    results: list[SearchResult]
    # Respuesta ya sintetizada, si el proveedor la da (Tavily sí, DuckDuckGo
    # no). Cuando existe, le ahorra al modelo tener que deducirla.
    answer: str | None = None

    def as_text(self) -> str:
        """Formato pensado para que lo lea el modelo, no una persona."""
        if not self.results and not self.answer:
            return "La búsqueda no devolvió resultados."

        parts = []
        if self.answer:
            parts.append(f"Resumen: {self.answer}")
        for index, result in enumerate(self.results, start=1):
            parts.append(f"{index}. {result.title}\n   {result.snippet}\n   Fuente: {result.url}")
        return "\n".join(parts)


def _search_duckduckgo(query: str, max_results: int, region: str) -> SearchResponse:
    try:
        from ddgs import DDGS
    except ImportError as exc:  # pragma: no cover — dependencia declarada en requirements
        raise WebSearchError(
            "Falta la librería 'ddgs'. Instalá las dependencias con: pip install -r requirements.txt"
        ) from exc

    try:
        raw = list(DDGS().text(query, region=region, max_results=max_results))
    except Exception as exc:  # noqa: BLE001 — la librería lanza excepciones propias variadas
        raise WebSearchError(
            f"DuckDuckGo no respondió ({exc}). Suele ser un límite de frecuencia: "
            "esperá un momento, o configurá WEB_SEARCH_PROVIDER=tavily."
        ) from exc

    return SearchResponse(
        results=[
            SearchResult(
                title=item.get("title", ""),
                snippet=item.get("body", ""),
                url=item.get("href", ""),
            )
            for item in raw
        ]
    )


def _search_tavily(query: str, max_results: int, api_key: str) -> SearchResponse:
    if not api_key:
        raise WebSearchNotConfigured(
            "TAVILY_API_KEY vacía. Creá una cuenta gratis en https://tavily.com "
            "(1.000 consultas/mes) y poné la key en backend/.env, o usá "
            "WEB_SEARCH_PROVIDER=duckduckgo, que no necesita nada."
        )

    response = requests.post(
        "https://api.tavily.com/search",
        json={
            "api_key": api_key,
            "query": query,
            "max_results": max_results,
            # Tavily puede sintetizar una respuesta a partir de las fuentes;
            # es la ventaja principal sobre raspar resultados sueltos.
            "include_answer": True,
            "search_depth": "basic",
        },
        timeout=_TIMEOUT,
    )
    if response.status_code == 401:
        raise WebSearchNotConfigured("Tavily rechazó la API key (401). Revisá TAVILY_API_KEY en .env.")
    response.raise_for_status()
    payload = response.json()

    return SearchResponse(
        answer=payload.get("answer") or None,
        results=[
            SearchResult(
                title=item.get("title", ""),
                snippet=item.get("content", ""),
                url=item.get("url", ""),
            )
            for item in payload.get("results", [])
        ],
    )


def search_web(
    query: str,
    provider: str = "duckduckgo",
    api_key: str = "",
    max_results: int = 5,
    region: str = "es-es",
) -> SearchResponse:
    if provider == "tavily":
        return _search_tavily(query, max_results, api_key)
    return _search_duckduckgo(query, max_results, region)
