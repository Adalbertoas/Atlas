"""Notificaciones persistidas (Fase 7) + suscripciones de Web Push (Fase 22).

Fase 7 dejó Web Push fuera de alcance porque HTTPS todavía no estaba
configurado para acceso por red local. Eso cambió en la Fase 16
(certs/dev-cert.pem), así que ahora sí hay contexto seguro para que los
navegadores acepten `PushManager.subscribe()`. El guardado en `Notification`
sigue existiendo igual (la lista de notificaciones "en la app" no
desaparece): Web Push se suma para avisar aunque la app esté cerrada, no
la reemplaza.
"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class Notification(Base):
    __tablename__ = "notifications"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    message: Mapped[str] = mapped_column(Text)
    read: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc)
    )


class PushSubscription(Base):
    """Una fila por navegador/dispositivo suscripto (sistema de un solo
    usuario, pero el mismo usuario puede tener el celular y el dashboard
    suscriptos a la vez — de ahí que sea una tabla y no un campo único)."""

    __tablename__ = "push_subscriptions"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    # URL única que identifica esta suscripción ante el servicio push del
    # navegador (FCM, Mozilla Push, etc.) — es la clave natural: el mismo
    # navegador vuelve a mandar el mismo endpoint si ya estaba suscripto.
    endpoint: Mapped[str] = mapped_column(String(700), unique=True)
    p256dh: Mapped[str] = mapped_column(String(200))
    auth: Mapped[str] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc)
    )
