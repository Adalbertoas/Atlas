"""Tests de la búsqueda web (Fase 19).

Mockean la red: no salen a internet ni dependen de tener una API key, igual
criterio que el resto de las integraciones externas.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from app.integrations.web_search import (
    SearchResponse,
    SearchResult,
    WebSearchError,
    WebSearchNotConfigured,
    search_web,
)
from app.tools.base import ToolContext
from app.tools.knowledge.search_web import SearchWebTool


# ---------- formato para el modelo ----------


def test_results_are_formatted_with_sources():
    """El modelo tiene que poder citar de dónde salió cada dato."""
    response = SearchResponse(results=[SearchResult("Titulo", "Resumen", "https://x.com")])
    text = response.as_text()
    assert "Titulo" in text and "Resumen" in text and "https://x.com" in text


def test_answer_is_shown_first_when_available():
    """Tavily sintetiza una respuesta; ponerla adelante le ahorra al modelo
    tener que deducirla de los fragmentos."""
    response = SearchResponse(
        answer="La respuesta corta.", results=[SearchResult("T", "S", "https://x.com")]
    )
    assert response.as_text().startswith("Resumen: La respuesta corta.")


def test_empty_response_says_so():
    assert "no devolvió resultados" in SearchResponse(results=[]).as_text()


# ---------- DuckDuckGo ----------


def test_duckduckgo_maps_fields():
    fake = MagicMock()
    fake.text.return_value = [
        {"title": "Mundial 2022", "body": "Argentina campeón", "href": "https://ejemplo.com"}
    ]
    with patch("ddgs.DDGS", return_value=fake):
        response = search_web("quien gano el mundial", provider="duckduckgo")

    assert len(response.results) == 1
    assert response.results[0].title == "Mundial 2022"
    assert response.results[0].url == "https://ejemplo.com"
    assert response.answer is None  # DuckDuckGo no sintetiza


def test_duckduckgo_failure_suggests_the_alternative():
    """El fallo más común es el límite de frecuencia; el mensaje tiene que
    decir qué hacer, no solo que falló."""
    fake = MagicMock()
    fake.text.side_effect = Exception("Ratelimit")
    with patch("ddgs.DDGS", return_value=fake):
        with pytest.raises(WebSearchError, match="tavily"):
            search_web("algo", provider="duckduckgo")


# ---------- Tavily ----------


def test_tavily_requires_api_key():
    with pytest.raises(WebSearchNotConfigured, match="TAVILY_API_KEY"):
        search_web("algo", provider="tavily", api_key="")


def test_tavily_returns_answer_and_results():
    response_mock = MagicMock()
    response_mock.status_code = 200
    response_mock.raise_for_status = MagicMock()
    response_mock.json.return_value = {
        "answer": "Argentina ganó el Mundial 2022.",
        "results": [{"title": "Final", "content": "Ganó por penales", "url": "https://ejemplo.com"}],
    }

    with patch("requests.post", return_value=response_mock):
        response = search_web("mundial 2022", provider="tavily", api_key="fake-key")

    assert response.answer == "Argentina ganó el Mundial 2022."
    assert response.results[0].url == "https://ejemplo.com"


def test_tavily_bad_key_is_reported_clearly():
    response_mock = MagicMock()
    response_mock.status_code = 401
    with patch("requests.post", return_value=response_mock):
        with pytest.raises(WebSearchNotConfigured, match="401"):
            search_web("algo", provider="tavily", api_key="key-mala")


def test_unknown_provider_falls_back_to_duckduckgo():
    """Un WEB_SEARCH_PROVIDER mal escrito no debe dejar a ATLAS sin búsqueda."""
    fake = MagicMock()
    fake.text.return_value = []
    with patch("ddgs.DDGS", return_value=fake) as ddgs:
        search_web("algo", provider="proveedor-inexistente")
    ddgs.assert_called_once()


# ---------- tool ----------


def test_tool_rejects_empty_query(db_session):
    result = SearchWebTool().execute({"query": "  "}, ToolContext(db=db_session))
    assert not result.success


def test_tool_returns_formatted_results(db_session):
    fake = MagicMock()
    fake.text.return_value = [{"title": "T", "body": "B", "href": "https://x.com"}]
    with patch("ddgs.DDGS", return_value=fake):
        result = SearchWebTool().execute({"query": "algo"}, ToolContext(db=db_session))

    assert result.success
    assert "https://x.com" in result.data


def test_tool_surfaces_errors_instead_of_raising(db_session):
    """Una búsqueda fallida no debe tumbar el turno de conversación entero."""
    fake = MagicMock()
    fake.text.side_effect = Exception("boom")
    with patch("ddgs.DDGS", return_value=fake):
        result = SearchWebTool().execute({"query": "algo"}, ToolContext(db=db_session))

    assert not result.success
    assert result.error


def test_tool_description_tells_the_model_when_to_use_it():
    """Sin esta guía el modelo busca de más (lento y ruidoso) o de menos
    (responde desactualizado). La descripción es la única señal que tiene."""
    description = SearchWebTool().description.lower()
    assert "actual" in description
    assert "wikipedia" in description  # debe saber cuándo NO usar esta
