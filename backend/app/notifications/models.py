"""Notificaciones persistidas (Fase 7).

Push real (Web Push/VAPID) queda fuera de alcance — requiere HTTPS, que no
está configurado para acceso por red local. En su lugar, cada evento
NOTIFICATION_CREATED del Event Bus se guarda acá; el cliente móvil las lista
al abrir/refrescar la app. Es "notificaciones en la app", no push del
sistema operativo — simplificación explícita, no a medias.
"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, Text
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
