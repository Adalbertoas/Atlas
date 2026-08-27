from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy.orm import Session

from app.api.deps import get_db_session
from app.reminders import service
from app.reminders.schemas import ReminderCreate, ReminderOut
from app.security.auth import get_current_user

router = APIRouter(prefix="/reminders", tags=["reminders"])


@router.get("", response_model=list[ReminderOut])
def list_reminders(
    pending_only: bool = False,
    db: Session = Depends(get_db_session),
    _user: str = Depends(get_current_user),
) -> list[ReminderOut]:
    return service.list_reminders(db, pending_only=pending_only)


@router.post("", response_model=ReminderOut, status_code=201)
def create_reminder(
    body: ReminderCreate,
    db: Session = Depends(get_db_session),
    _user: str = Depends(get_current_user),
) -> ReminderOut:
    return service.create_reminder(db, text=body.text, due_at=body.due_at)


@router.patch("/{reminder_id}/done")
def mark_done(
    reminder_id: int,
    db: Session = Depends(get_db_session),
    _user: str = Depends(get_current_user),
) -> dict:
    if not service.mark_done(db, reminder_id):
        raise HTTPException(status_code=404, detail="Recordatorio no encontrado.")
    return {"done": True}


# response_class=Response: sin esto FastAPI intenta serializar un cuerpo JSON
# y falla, porque 204 no admite cuerpo.
@router.delete("/{reminder_id}", status_code=204, response_class=Response)
def delete_reminder(
    reminder_id: int,
    db: Session = Depends(get_db_session),
    _user: str = Depends(get_current_user),
) -> Response:
    if not service.delete_reminder(db, reminder_id):
        raise HTTPException(status_code=404, detail="Recordatorio no encontrado.")
    return Response(status_code=204)
