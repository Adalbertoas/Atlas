"""Construye el VisionProvider activo (mismo patrón que
app/smart_home/provider_factory.py)."""
from __future__ import annotations

from functools import lru_cache

from app.config import get_settings
from app.vision.base import VisionProvider


@lru_cache
def get_vision_provider() -> VisionProvider:
    settings = get_settings()
    if settings.vision_provider == "anthropic":
        from app.vision.anthropic_provider import AnthropicVisionProvider

        return AnthropicVisionProvider(api_key=settings.anthropic_api_key, model=settings.anthropic_model)

    from app.vision.mock_provider import MockVisionProvider

    return MockVisionProvider()
