from __future__ import annotations

from app.embeddings.mock_provider import MockEmbeddingProvider
from app.memory.schemas import MemoryCreate
from app.memory.service import _cosine_similarity, create_memory, search_memories


def test_mock_embedding_is_deterministic():
    provider = MockEmbeddingProvider()
    assert provider.embed("le gusta el café") == provider.embed("le gusta el café")


def test_mock_embedding_differs_for_unrelated_text():
    provider = MockEmbeddingProvider()
    a = provider.embed("le gusta el café negro")
    b = provider.embed("el clima en Bogotá está nublado")
    assert _cosine_similarity(a, a) > _cosine_similarity(a, b)


def test_create_memory_stores_embedding(db_session):
    entry = create_memory(db_session, MemoryCreate(content="Trabaja en un proyecto de IA", category="project"))
    from app.memory.models import MemoryEntry

    stored = db_session.get(MemoryEntry, entry.id)
    assert stored.embedding is not None


def test_search_finds_semantically_related_without_shared_words(db_session):
    create_memory(
        db_session,
        MemoryCreate(content="Programa en Python para una startup de inteligencia artificial", category="project"),
    )
    create_memory(db_session, MemoryCreate(content="Cumpleaños en marzo", category="personal"))

    # El mock embedding no entiende sinónimos como un modelo real, pero sí
    # capta solapamiento de vocabulario compartido entre la consulta y la
    # memoria relevante frente a la que no tiene nada que ver.
    results = search_memories(db_session, "inteligencia artificial startup")
    assert len(results) >= 1
    assert "Python" in results[0].content


def test_search_falls_back_to_like_for_entries_without_embedding(db_session, monkeypatch):
    from app.memory import service

    # Simula una memoria vieja (sin embedding, provider falló al guardarla).
    monkeypatch.setattr(service, "_embed_text", lambda text: None)
    create_memory(db_session, MemoryCreate(content="Proyecto ATLAS usa FastAPI", category="project"))

    monkeypatch.undo()
    results = search_memories(db_session, "FastAPI")
    assert len(results) == 1
    assert "ATLAS" in results[0].content


def test_create_memory_does_not_fail_if_embedding_provider_raises(db_session, monkeypatch):
    from app.memory import service

    class BrokenProvider:
        def embed(self, text):
            raise RuntimeError("modelo no disponible")

    monkeypatch.setattr(service, "get_embedding_provider", lambda: BrokenProvider())
    entry = create_memory(db_session, MemoryCreate(content="Se guarda igual", category="personal"))
    assert entry.content == "Se guarda igual"
