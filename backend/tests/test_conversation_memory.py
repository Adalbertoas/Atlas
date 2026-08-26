from __future__ import annotations

from app.memory.conversation_service import append_message, get_history


def test_append_and_get_history_in_order(db_session):
    append_message(db_session, "conv-1", "user", "Hola")
    append_message(db_session, "conv-1", "assistant", "Hola, ¿en qué te ayudo?")
    append_message(db_session, "conv-1", "user", "¿Qué hora es?")

    history = get_history(db_session, "conv-1")
    assert [m.content for m in history] == ["Hola", "Hola, ¿en qué te ayudo?", "¿Qué hora es?"]


def test_get_history_is_scoped_per_conversation(db_session):
    append_message(db_session, "conv-a", "user", "mensaje A")
    append_message(db_session, "conv-b", "user", "mensaje B")

    history_a = get_history(db_session, "conv-a")
    assert len(history_a) == 1
    assert history_a[0].content == "mensaje A"


def test_get_history_respects_limit(db_session):
    for i in range(5):
        append_message(db_session, "conv-1", "user", f"mensaje {i}")

    history = get_history(db_session, "conv-1", limit=2)
    assert len(history) == 2
    # Deben ser los 2 más recientes, en orden cronológico.
    assert [m.content for m in history] == ["mensaje 3", "mensaje 4"]
