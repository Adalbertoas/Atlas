from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.deps import get_db_session
from app.config import get_settings
from app.notifications import service
from app.notifications.schemas import NotificationOut, PushSubscriptionIn
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


# ---------- Web Push (Fase 22) ----------


@router.get("/push/public-key")
def get_push_public_key(_user: str = Depends(get_current_user)) -> dict:
    """El cliente necesita esta clave para `PushManager.subscribe()`
    (applicationServerKey). Requiere login igual que el resto: no tiene
    sentido exponerla a quien no puede ni ver notificaciones."""
    settings = get_settings()
    return {"public_key": settings.vapid_public_key}


@router.post("/push/subscribe")
def subscribe_push(
    subscription: PushSubscriptionIn,
    db: Session = Depends(get_db_session),
    _user: str = Depends(get_current_user),
) -> dict:
    service.save_push_subscription(
        db,
        endpoint=subscription.endpoint,
        p256dh=subscription.keys.p256dh,
        auth=subscription.keys.auth,
    )
    return {"subscribed": True}


@router.delete("/push/subscribe")
def unsubscribe_push(
    endpoint: str,
    db: Session = Depends(get_db_session),
    _user: str = Depends(get_current_user),
) -> dict:
    service.remove_push_subscription(db, endpoint)
    return {"subscribed": False}
