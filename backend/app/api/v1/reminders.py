from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.deps import get_db_session
from app.reminders import service

router = APIRouter(prefix="/reminders", tags=["reminders"])


@router.get("")
def list_reminders(db: Session = Depends(get_db_session)) -> list[dict]:
    """Recordatorios pendientes, del más próximo al más lejano."""
    return [service.to_dict(reminder) for reminder in service.list_pending(db)]


@router.delete("/{reminder_id}")
def cancel_reminder(reminder_id: int, db: Session = Depends(get_db_session)) -> dict:
    if not service.cancel_reminder(db, reminder_id):
        raise HTTPException(status_code=404, detail="Recordatorio no encontrado.")
    return {"deleted": True}
