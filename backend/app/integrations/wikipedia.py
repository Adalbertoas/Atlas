"""Cliente de Wikipedia (sin API key — es pública).

Dos pasos: opensearch (encuentra el título exacto del artículo más
relevante para una búsqueda ambigua/con errores de tipeo) y luego el
endpoint REST de resumen (que trae el extracto en texto plano, ya
recortado a la intro del artículo).
"""
from __future__ import annotations

from dataclasses import dataclass

import requests

_TIMEOUT = 10
# Wikimedia devuelve 403 sin un User-Agent descriptivo (política de etiqueta
# de su API: https://meta.wikimedia.org/wiki/User-Agent_policy) — el default
# de requests ("python-requests/x.y") lo bloquea directamente.
_HEADERS = {"User-Agent": "ATLAS-Assistant/1.0 (asistente personal, uso no comercial)"}


@dataclass
class WikipediaResult:
    title: str
    summary: str
    url: str


def search_wikipedia(query: str, lang: str = "es") -> WikipediaResult | None:
    """None si no se encontró ningún artículo razonable para la búsqueda."""
    opensearch = requests.get(
        f"https://{lang}.wikipedia.org/w/api.php",
        params={"action": "opensearch", "search": query, "limit": 1, "format": "json"},
        headers=_HEADERS,
        timeout=_TIMEOUT,
    )
    opensearch.raise_for_status()
    _, titles, _, urls = opensearch.json()
    if not titles:
        return None
    title = titles[0]

    summary_response = requests.get(
        f"https://{lang}.wikipedia.org/api/rest_v1/page/summary/{title}",
        headers=_HEADERS,
        timeout=_TIMEOUT,
    )
    if summary_response.status_code == 404:
        return None
    summary_response.raise_for_status()
    data = summary_response.json()

    return WikipediaResult(
        title=data.get("title", title),
        summary=data.get("extract", ""),
        url=urls[0] if urls else data.get("content_urls", {}).get("desktop", {}).get("page", ""),
    )
