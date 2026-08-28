"""Construye el EmbeddingProvider activo (mismo patrón que
app/vision/provider_factory.py y app/smart_home/provider_factory.py)."""
from __future__ import annotations

from functools import lru_cache

from app.config import get_settings
from app.embeddings.base import EmbeddingProvider


@lru_cache
def get_embedding_provider() -> EmbeddingProvider:
    settings = get_settings()
    if settings.embedding_provider == "fastembed":
        from app.embeddings.fastembed_provider import FastEmbedProvider

        return FastEmbedProvider(model_name=settings.embedding_model)

    from app.embeddings.mock_provider import MockEmbeddingProvider

    return MockEmbeddingProvider()
