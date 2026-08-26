from __future__ import annotations

from app.memory.schemas import MemoryCreate
from app.memory.service import create_memory, delete_memory, forget, list_memories, search_memories


def test_create_and_list_memory(db_session):
    create_memory(db_session, MemoryCreate(content="Le gusta el café negro", category="preference"))
    results = list_memories(db_session)
    assert len(results) == 1
    assert results[0].content == "Le gusta el café negro"


def test_search_memory_by_content(db_session):
    create_memory(db_session, MemoryCreate(content="Proyecto ATLAS usa FastAPI", category="project"))
    create_memory(db_session, MemoryCreate(content="Cumpleaños en marzo", category="personal"))

    results = search_memories(db_session, "FastAPI")
    assert len(results) == 1
    assert "ATLAS" in results[0].content


def test_delete_memory(db_session):
    entry = create_memory(db_session, MemoryCreate(content="Temporal", category="personal"))
    assert delete_memory(db_session, entry.id) is True
    assert delete_memory(db_session, entry.id) is False


def test_forget_removes_matching_entries(db_session):
    create_memory(db_session, MemoryCreate(content="Odia el ruido de las notificaciones", category="preference"))
    create_memory(db_session, MemoryCreate(content="Le gusta el silencio", category="preference"))

    removed = forget(db_session, "notificaciones")
    assert removed == 1
    assert len(list_memories(db_session)) == 1
