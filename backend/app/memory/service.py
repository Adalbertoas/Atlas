"""Servicio de memoria: guardar, consultar, listar y eliminar (sección 6).

Cubre explícitamente los dos flujos que pide el prompt maestro:
- "¿Qué recuerdas de mí?"      -> list_memories() / search_memories()
- "Olvida lo que te dije sobre X." -> forget(query=...)

No hay guardado automático de información sensible: solo se persiste lo que
llega a través de create_memory, que en el flujo de chat pasa siempre por
PermissionManager (LOW_RISK) antes de ejecutarse.
"""
from __future__ import annotations

import json
import math

from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.embeddings.provider_factory import get_embedding_provider
from app.memory.models import MemoryEntry
from app.memory.schemas import MemoryCreate, MemoryOut

# Umbral mínimo de similitud de coseno para considerar dos textos
# relacionados. Elegido por prueba manual con el modelo por defecto
# (all-MiniLM-L6-v2): por debajo de esto el ranking empieza a traer
# resultados sin relación real, solo ruido compartido del vocabulario.
_SIMILARITY_THRESHOLD = 0.35


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(y * y for y in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


def _embed_text(text: str) -> str | None:
    """Calcula el embedding de `text` como JSON, o None si el provider
    falla — nunca debe impedir que la memoria se guarde igual (el texto
    plano sigue sirviendo para el fallback de LIKE)."""
    try:
        vector = get_embedding_provider().embed(text)
        return json.dumps(vector)
    except Exception:
        return None


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
        embedding=_embed_text(data.content),
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
    """Búsqueda híbrida: combina coincidencia literal (LIKE, siempre barata y
    determinística) con similitud semántica por embedding, para encontrar
    memorias relacionadas aunque no compartan ninguna palabra con la
    consulta ("¿en qué trabajo?" -> "programo en Python para una startup").

    Las entradas sin embedding (memorias creadas antes de este campo, o si
    el provider falló al guardarlas) solo se encuentran por LIKE — no
    desaparecen, simplemente no participan del ranking semántico.
    """
    like = f"%{query_text}%"
    like_matches = {
        e.id: e
        for e in db.query(MemoryEntry)
        .filter(or_(MemoryEntry.content.ilike(like), MemoryEntry.tags.ilike(like)))
        .all()
    }

    query_vector = _embed_text(query_text)
    semantic_matches: dict[int, tuple[MemoryEntry, float]] = {}
    if query_vector is not None:
        query_embedding = json.loads(query_vector)
        candidates = db.query(MemoryEntry).filter(MemoryEntry.embedding.isnot(None)).all()
        for entry in candidates:
            score = _cosine_similarity(query_embedding, json.loads(entry.embedding))
            if score >= _SIMILARITY_THRESHOLD:
                semantic_matches[entry.id] = (entry, score)

    # LIKE es determinístico y siempre relevante: se prioriza (score 1.0) y
    # se completa con lo semántico, ordenado por similitud descendente.
    ranked_ids = list(like_matches.keys())
    for entry_id, (_entry, _score) in sorted(
        semantic_matches.items(), key=lambda kv: kv[1][1], reverse=True
    ):
        if entry_id not in like_matches:
            ranked_ids.append(entry_id)

    all_entries = {**like_matches, **{eid: e for eid, (e, _s) in semantic_matches.items()}}
    results = [all_entries[eid] for eid in ranked_ids[:limit]]
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
