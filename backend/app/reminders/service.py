"""CRUD de recordatorios (Fase 11)."""
from __future__ import annotations

from datetime import datetime

from sqlalchemy.orm import Session

from app.reminders.models import Reminder
from app.reminders.schemas import ReminderOut


def create_reminder(db: Session, text: str, due_at: datetime) -> ReminderOut:
    reminder = Reminder(text=text, due_at=due_at)
    db.add(reminder)
    db.commit()
    db.refresh(reminder)
    return ReminderOut.model_validate(reminder)


def list_reminders(db: Session, pending_only: bool = False, limit: int = 50) -> list[ReminderOut]:
    """Ordenados por vencimiento ascendente — el dashboard muestra "los
    próximos", no "los últimos creados" (al revés que notificaciones)."""
    query = db.query(Reminder)
    if pending_only:
        query = query.filter(Reminder.done.is_(False))
    entries = query.order_by(Reminder.due_at.asc()).limit(limit).all()
    return [ReminderOut.model_validate(r) for r in entries]


def mark_done(db: Session, reminder_id: int) -> bool:
    reminder = db.get(Reminder, reminder_id)
    if reminder is None:
        return False
    reminder.done = True
    db.commit()
    return True


def delete_reminder(db: Session, reminder_id: int) -> bool:
    reminder = db.get(Reminder, reminder_id)
    if reminder is None:
        return False
    db.delete(reminder)
    db.commit()
    return True
