from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.deps import get_db_session
from app.notifications import service
from app.notifications.schemas import NotificationOut
from app.security.auth import get_current_user

router = APIRouter(prefix="/notifications", tags=["notifications"])


@router.get("", response_model=list[NotificationOut])
def list_notifications(
    unread_only: bool = False,
    db: Session = Depends(get_db_session),
    _user: str = Depends(get_current_user),
) -> list[NotificationOut]:
    return service.list_notifications(db, unread_only=unread_only)


@router.patch("/{notification_id}/read")
def mark_read(
    notification_id: int,
    db: Session = Depends(get_db_session),
    _user: str = Depends(get_current_user),
) -> dict:
    ok = service.mark_read(db, notification_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Notificación no encontrada.")
    return {"read": True}
