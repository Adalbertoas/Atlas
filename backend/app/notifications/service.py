"""Persistencia de notificaciones + subscriber del Event Bus (Fase 7)."""
from __future__ import annotations

from sqlalchemy.orm import Session

from app.core.database import SessionLocal
from app.events.bus import Event, EventBus, EventType
from app.notifications.models import Notification
from app.notifications.schemas import NotificationOut


def list_notifications(db: Session, unread_only: bool = False) -> list[NotificationOut]:
    query = db.query(Notification).order_by(Notification.created_at.desc())
    if unread_only:
        query = query.filter(Notification.read.is_(False))
    return [NotificationOut.model_validate(n) for n in query.all()]


def mark_read(db: Session, notification_id: int) -> bool:
    notification = db.get(Notification, notification_id)
    if notification is None:
        return False
    notification.read = True
    db.commit()
    return True


def notify(events: EventBus, message: str) -> None:
    """Crea una notificación con un texto ya redactado (alertas, recordatorios, briefing)."""
    events.publish(Event(type=EventType.NOTIFICATION_CREATED, payload={"message": message}))


def _format_message(event: Event) -> str:
    payload = event.payload
    if "message" in payload:
        return str(payload["message"])
    if event.type == EventType.NOTIFICATION_CREATED and "routine" in payload:
        return f"Rutina '{payload['routine']}': {payload.get('reason', 'requiere tu atención.')}"
    return str(payload)


def register_notification_subscriber(events: EventBus) -> None:
    def handler(event: Event) -> None:
        db = SessionLocal()
        try:
            db.add(Notification(message=_format_message(event)))
            db.commit()
        finally:
            db.close()

    events.subscribe(EventType.NOTIFICATION_CREATED, handler)
