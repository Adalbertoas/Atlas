"""Modelo de memoria personal de ATLAS (sección 6 del prompt maestro).

V1 implementa un único modelo genérico `MemoryEntry` con una `category` para
distinguir tipos (personal, preference, project, conversation_summary...).
Esto cubre "memoria personal", "de preferencias" y "de proyectos" sin crear
tablas separadas todavía; si el volumen o las consultas lo justifican más
adelante, se pueden especializar sin romper la API pública del servicio.
"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import DateTime, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class MemoryEntry(Base):
    __tablename__ = "memory_entries"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    category: Mapped[str] = mapped_column(String(50), default="personal")
    content: Mapped[str] = mapped_column(Text)
    tags: Mapped[str] = mapped_column(String(300), default="")  # CSV simple para V1
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc)
    )


class ConversationMessage(Base):
    """Historial de una conversación de chat (distinto de MemoryEntry: esto es
    el "qué se dijo", no "qué se debe recordar" — sección 6 del prompt
    maestro trata memoria de conversación y memoria personal como conceptos
    separados)."""

    __tablename__ = "conversation_messages"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    conversation_id: Mapped[str] = mapped_column(String(64), index=True)
    role: Mapped[str] = mapped_column(String(20))  # "user" | "assistant"
    content: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc)
    )
