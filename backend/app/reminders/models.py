"""Recordatorios personales (Fase 11).

Distintos de las rutinas del Automation Engine (Fase 6): una rutina
*ejecuta acciones* al dispararse (apagar una luz, correr tools), un
recordatorio solo *avisa* — no tiene acciones asociadas. Se separan en vez
de forzar el mismo modelo porque el usuario los piensa distinto ("recordame
llamar al médico" no es "automatizá algo").
"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class Reminder(Base):
    __tablename__ = "reminders"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    text: Mapped[str] = mapped_column(Text)
    # Naive UTC, igual que el resto del proyecto (columnas DateTime sin tz).
    due_at: Mapped[datetime] = mapped_column(DateTime, index=True)
    done: Mapped[bool] = mapped_column(Boolean, default=False)
    # Si ya se avisó que venció. Separado de `done`: un recordatorio puede
    # haber sonado sin que lo hayas dado por hecho, y sin este campo el
    # scheduler volvería a avisar cada 30 segundos para siempre.
    notified: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc)
    )
