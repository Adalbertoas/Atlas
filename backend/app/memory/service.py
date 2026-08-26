"""Servicio de memoria: guardar, consultar, listar y eliminar (sección 6).

Cubre explícitamente los dos flujos que pide el prompt maestro:
- "¿Qué recuerdas de mí?"      -> list_memories() / search_memories()
- "Olvida lo que te dije sobre X." -> forget(query=...)

No hay guardado automático de información sensible: solo se persiste lo que
llega a través de create_memory, que en el flujo de chat pasa siempre por
PermissionManager (LOW_RISK) antes de ejecutarse.
"""
from __future__ import annotations

from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.memory.models import MemoryEntry
from app.memory.schemas import MemoryCreate, MemoryOut


def _to_out(entry: MemoryEntry) -> MemoryOut:
    tags = [t for t in (entry.tags or "").split(",") if t]
    return MemoryOut(
        id=entry.id,
        category=entry.category,
        content=entry.content,
        tags=tags,
        created_at=entry.created_at,
    )


def create_memory(db: Session, data: MemoryCreate) -> MemoryOut:
    entry = MemoryEntry(
        category=data.category,
        content=data.content,
        tags=",".join(data.tags),
    )
    db.add(entry)
    db.commit()
    db.refresh(entry)
    return _to_out(entry)


def list_memories(db: Session, category: str | None = None, limit: int = 50) -> list[MemoryOut]:
    query = db.query(MemoryEntry).order_by(MemoryEntry.created_at.desc())
    if category:
        query = query.filter(MemoryEntry.category == category)
    return [_to_out(e) for e in query.limit(limit).all()]


def search_memories(db: Session, query_text: str, limit: int = 20) -> list[MemoryOut]:
    like = f"%{query_text}%"
    results = (
        db.query(MemoryEntry)
        .filter(or_(MemoryEntry.content.ilike(like), MemoryEntry.tags.ilike(like)))
        .order_by(MemoryEntry.created_at.desc())
        .limit(limit)
        .all()
    )
    return [_to_out(e) for e in results]


def delete_memory(db: Session, memory_id: int) -> bool:
    entry = db.get(MemoryEntry, memory_id)
    if entry is None:
        return False
    db.delete(entry)
    db.commit()
    return True


def forget(db: Session, query_text: str) -> int:
    """Elimina todas las memorias que coincidan con query_text. Devuelve cuántas se borraron."""
    like = f"%{query_text}%"
    matches = db.query(MemoryEntry).filter(
        or_(MemoryEntry.content.ilike(like), MemoryEntry.tags.ilike(like))
    ).all()
    count = len(matches)
    for entry in matches:
        db.delete(entry)
    db.commit()
    return count
