from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.api.deps import get_db_session
from app.memory import service
from app.memory.schemas import MemoryCreate, MemoryOut

router = APIRouter(prefix="/memory", tags=["memory"])


@router.post("", response_model=MemoryOut)
def create(body: MemoryCreate, db: Session = Depends(get_db_session)) -> MemoryOut:
    return service.create_memory(db, body)


@router.get("", response_model=list[MemoryOut])
def list_all(
    category: str | None = None,
    limit: int = Query(50, le=200),
    db: Session = Depends(get_db_session),
) -> list[MemoryOut]:
    return service.list_memories(db, category=category, limit=limit)


@router.get("/search", response_model=list[MemoryOut])
def search(q: str, db: Session = Depends(get_db_session)) -> list[MemoryOut]:
    return service.search_memories(db, q)


@router.delete("/{memory_id}")
def delete(memory_id: int, db: Session = Depends(get_db_session)) -> dict:
    ok = service.delete_memory(db, memory_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Memoria no encontrada.")
    return {"deleted": True}


@router.post("/forget")
def forget(q: str, db: Session = Depends(get_db_session)) -> dict:
    count = service.forget(db, q)
    return {"forgotten": count}
