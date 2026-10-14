"""Recordatorios y temporizadores.

Un recordatorio es un mensaje con una fecha de vencimiento; al llegar, se
convierte en una notificación (app/core/background.py lo revisa cada pocos
segundos). Puede repetirse a diario, de lunes a viernes o cada semana.

Las fechas se guardan en UTC sin tzinfo (como el resto de las tablas), pero
la repetición se calcula en hora local para que "todos los días a las 9"
siga siendo a las 9 cuando cambia el horario de verano.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import Boolean, DateTime, String, Text
from sqlalchemy.orm import Mapped, Session, mapped_column

from app.core.database import Base
from app.events.bus import EventBus
from app.notifications.service import notify

REPEATS = ["none", "daily", "weekdays", "weekly"]
_REPEAT_LABELS = {"daily": "todos los días", "weekdays": "de lunes a viernes", "weekly": "cada semana"}
WEEKDAYS = {
    "monday": 0, "lunes": 0,
    "tuesday": 1, "martes": 1,
    "wednesday": 2, "miercoles": 2, "miércoles": 2,
    "thursday": 3, "jueves": 3,
    "friday": 4, "viernes": 4,
    "saturday": 5, "sabado": 5, "sábado": 5,
    "sunday": 6, "domingo": 6,
}  # fmt: skip


def utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def to_local(moment: datetime) -> datetime:
    """UTC sin tzinfo -> hora local con tzinfo."""
    return moment.replace(tzinfo=timezone.utc).astimezone()


def to_utc(moment: datetime) -> datetime:
    """Hora local (con o sin tzinfo) -> UTC sin tzinfo."""
    return moment.astimezone(timezone.utc).replace(tzinfo=None)


class Reminder(Base):
    __tablename__ = "reminders"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    message: Mapped[str] = mapped_column(Text)
    due_at: Mapped[datetime] = mapped_column(DateTime)
    repeat: Mapped[str] = mapped_column(String(20), default="none")
    done: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


def describe(reminder: Reminder) -> str:
    local = to_local(reminder.due_at)
    when = local.strftime("%d/%m %H:%M")
    repeat = f", {_REPEAT_LABELS[reminder.repeat]}" if reminder.repeat in _REPEAT_LABELS else ""
    return f"{reminder.message} — {when}{repeat}"


def to_dict(reminder: Reminder) -> dict:
    return {
        "id": reminder.id,
        "message": reminder.message,
        "due_at": reminder.due_at.isoformat() + "Z",
        "repeat": reminder.repeat,
        "description": describe(reminder),
    }


def resolve_due(
    now_local: datetime,
    in_seconds: float | None = None,
    at: str | None = None,
    weekday: str | None = None,
) -> datetime:
    """Calcula el vencimiento en hora local. Lanza ValueError si no se entiende.

    `at` acepta "HH:MM" (la próxima vez que sea esa hora) o "AAAA-MM-DD HH:MM".
    `weekday` (nombre del día, en español o inglés) lo lleva al próximo día de esa semana.
    """
    if in_seconds is not None:
        if in_seconds <= 0:
            raise ValueError("El tiempo del recordatorio debe ser mayor a cero.")
        return now_local + timedelta(seconds=in_seconds)
    if not at:
        raise ValueError("Indicá cuándo: en cuántos minutos, o a qué hora.")

    text = at.strip().replace("T", " ")
    try:
        if len(text) <= 5:
            hour, minute = (int(part) for part in text.split(":"))
            due = now_local.replace(hour=hour, minute=minute, second=0, microsecond=0)
            if due <= now_local and not weekday:
                due += timedelta(days=1)
        else:
            parsed = datetime.strptime(text[:16], "%Y-%m-%d %H:%M")
            due = parsed.replace(tzinfo=now_local.tzinfo)
    except ValueError as exc:
        raise ValueError(f"No entendí la hora '{at}'. Usá 'HH:MM' o 'AAAA-MM-DD HH:MM'.") from exc

    if weekday:
        target = WEEKDAYS.get(weekday.strip().lower())
        if target is None:
            raise ValueError(f"No entendí el día '{weekday}'.")
        due += timedelta(days=(target - due.weekday()) % 7)
        if due <= now_local:
            due += timedelta(days=7)
    if due <= now_local:
        raise ValueError("Esa fecha ya pasó.")
    return due


def create_reminder(db: Session, message: str, due_local: datetime, repeat: str = "none") -> Reminder:
    message = message.strip()
    if not message:
        raise ValueError("El recordatorio necesita un mensaje.")
    if repeat not in REPEATS:
        raise ValueError(f"Repetición '{repeat}' no reconocida. Opciones: {', '.join(REPEATS)}")
    reminder = Reminder(message=message, due_at=to_utc(due_local), repeat=repeat)
    db.add(reminder)
    db.commit()
    db.refresh(reminder)
    return reminder


def list_pending(db: Session) -> list[Reminder]:
    return db.query(Reminder).filter(Reminder.done.is_(False)).order_by(Reminder.due_at).all()


def cancel_reminder(db: Session, reminder_id: int) -> bool:
    reminder = db.get(Reminder, reminder_id)
    if reminder is None or reminder.done:
        return False
    db.delete(reminder)
    db.commit()
    return True


def _next_occurrence(due_at: datetime, repeat: str, now: datetime) -> datetime:
    """Próximo vencimiento posterior a `now` de un recordatorio que se repite."""
    local = to_local(due_at)
    step = timedelta(days=7 if repeat == "weekly" else 1)
    while True:
        # Se suma sobre la hora "de pared" y se vuelve a ubicar en la zona local.
        local = (local.replace(tzinfo=None) + step).astimezone()
        if repeat == "weekdays" and local.weekday() >= 5:
            continue
        if to_utc(local) > now:
            return to_utc(local)


def fire_due(db: Session, events: EventBus, now: datetime | None = None) -> int:
    """Notifica los recordatorios vencidos. Devuelve cuántos disparó."""
    now = now or utcnow()
    due = db.query(Reminder).filter(Reminder.done.is_(False), Reminder.due_at <= now).all()
    for reminder in due:
        if reminder.repeat == "none":
            reminder.done = True
        else:
            reminder.due_at = _next_occurrence(reminder.due_at, reminder.repeat, now)
    db.commit()
    for reminder in due:
        notify(events, f"⏰ Recordatorio: {reminder.message}")
    return len(due)
