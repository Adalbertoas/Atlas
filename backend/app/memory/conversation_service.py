"""Servicio de memoria de conversación multi-turno (sección 6, Fase 2)."""
from __future__ import annotations

from sqlalchemy.orm import Session

from app.memory.models import ConversationMessage


def get_history(db: Session, conversation_id: str, limit: int = 20) -> list[ConversationMessage]:
    """Últimos `limit` mensajes de la conversación, en orden cronológico."""
    rows = (
        db.query(ConversationMessage)
        .filter(ConversationMessage.conversation_id == conversation_id)
        .order_by(ConversationMessage.created_at.desc())
        .limit(limit)
        .all()
    )
    return list(reversed(rows))


def append_message(db: Session, conversation_id: str, role: str, content: str) -> ConversationMessage:
    entry = ConversationMessage(conversation_id=conversation_id, role=role, content=content)
    db.add(entry)
    db.commit()
    db.refresh(entry)
    return entry
