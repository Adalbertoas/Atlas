"""Construcción de proveedores de IA según la configuración.

Vive aparte de app.api.deps para que las tools (que se registran al importar
app.tools.registry) puedan pedir un proveedor sin importar la capa de la API.
"""
from __future__ import annotations

from app.ai.base import AIProvider
from app.config import get_settings


def build_ai_provider(model: str | None = None, max_tokens: int | None = None) -> AIProvider:
    """Proveedor configurado en AI_PROVIDER. `model` y `max_tokens` permiten a una
    tarea puntual (ej. dibujar un SVG) usar otro modelo o respuestas más largas."""
    settings = get_settings()
    if settings.ai_provider == "ollama":
        from app.ai.ollama_provider import OllamaProvider

        return OllamaProvider(model=model or settings.ollama_model, base_url=settings.ollama_base_url)
    if settings.ai_provider == "anthropic":
        from app.ai.anthropic_provider import AnthropicProvider

        return AnthropicProvider(
            api_key=settings.anthropic_api_key,
            model=model or settings.anthropic_model,
            max_tokens=max_tokens or 1024,
        )
    from app.ai.mock_provider import MockProvider

    return MockProvider()
