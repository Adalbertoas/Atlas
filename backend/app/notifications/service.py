"""Persistencia de notificaciones + subscriber del Event Bus (Fase 7) +
envío real de Web Push (Fase 22)."""
from __future__ import annotations

import logging

from sqlalchemy.orm import Session

from app.config import get_settings
from app.core.database import SessionLocal
from app.events.bus import Event, EventBus, EventType
from app.notifications.models import Notification, PushSubscription
from app.notifications.schemas import NotificationOut

logger = logging.getLogger(__name__)


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


# ---------- Web Push (Fase 22) ----------


def save_push_subscription(db: Session, endpoint: str, p256dh: str, auth: str) -> None:
    """Idempotente: si el navegador ya estaba suscripto (mismo endpoint),
    actualiza las claves en vez de duplicar la fila — puede pasar si el
    navegador rota las claves sin cambiar el endpoint."""
    existing = db.query(PushSubscription).filter(PushSubscription.endpoint == endpoint).first()
    if existing:
        existing.p256dh = p256dh
        existing.auth = auth
    else:
        db.add(PushSubscription(endpoint=endpoint, p256dh=p256dh, auth=auth))
    db.commit()


def remove_push_subscription(db: Session, endpoint: str) -> bool:
    existing = db.query(PushSubscription).filter(PushSubscription.endpoint == endpoint).first()
    if existing is None:
        return False
    db.delete(existing)
    db.commit()
    return True


def send_web_push(db: Session, message: str) -> None:
    """Manda `message` a todas las suscripciones guardadas. Best-effort: una
    suscripción que falla no debe frenar las demás ni romper el flujo que la
    llama (el guardado en `Notification` ya es la fuente de verdad — esto es
    un aviso extra, no la única forma de enterarse)."""
    settings = get_settings()
    if not settings.vapid_public_key or not settings.vapid_private_key:
        return  # no configurado: mismo criterio que YouTube/Spotify/AudD, sin romper el resto

    from pywebpush import WebPushException, webpush

    subscriptions = db.query(PushSubscription).all()
    for sub in subscriptions:
        subscription_info = {
            "endpoint": sub.endpoint,
            "keys": {"p256dh": sub.p256dh, "auth": sub.auth},
        }
        try:
            webpush(
                subscription_info=subscription_info,
                data=message,
                vapid_private_key=settings.vapid_private_key,
                vapid_claims={"sub": f"mailto:{settings.vapid_contact_email}"},
            )
        except WebPushException as exc:
            status_code = getattr(exc.response, "status_code", None)
            if status_code in (404, 410):
                # El navegador se desuscribió (desinstaló la app, borró
                # datos del sitio, etc.) — el servicio push lo confirma con
                # este código. Limpiar la suscripción muerta en vez de
                # seguir intentando mandarle para siempre.
                db.delete(sub)
                db.commit()
            else:
                logger.warning("Web Push falló para %s: %s", sub.endpoint[:50], exc)


def _format_message(event: Event) -> str:
    payload = event.payload
    if event.type == EventType.NOTIFICATION_CREATED:
        if "reminder" in payload:
            return f"Recordatorio: {payload['reminder']}"
        if "routine" in payload:
            return f"Rutina '{payload['routine']}': {payload.get('reason', 'requiere tu atención.')}"
    return str(payload)


def register_notification_subscriber(events: EventBus) -> None:
    def handler(event: Event) -> None:
        db = SessionLocal()
        try:
            message = _format_message(event)
            db.add(Notification(message=message))
            db.commit()
            send_web_push(db, message)
        finally:
            db.close()

    events.subscribe(EventType.NOTIFICATION_CREATED, handler)
