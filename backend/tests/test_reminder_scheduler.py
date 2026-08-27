"""Tests del aviso de recordatorios vencidos (Fase 20).

El hueco que cierran: hasta acá se podían crear recordatorios pero nada
revisaba si vencían, así que nunca avisaban.
"""
from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from app.events.bus import Event, EventBus, EventType
from app.reminders import service
from app.reminders.models import Reminder
from app.reminders.scheduler import ReminderScheduler


@pytest.fixture()
def captured_events(monkeypatch, db_session):
    """Captura lo que publica el scheduler y lo hace trabajar sobre la base
    de test en vez de la real."""
    events: list[Event] = []
    bus = EventBus()
    bus.publish = events.append  # type: ignore[method-assign]

    # El scheduler abre su propia sesión (corre en background); se la
    # redirige a la de test.
    monkeypatch.setattr("app.reminders.scheduler.SessionLocal", lambda: db_session)
    monkeypatch.setattr(db_session, "close", lambda: None)
    return events, bus, db_session


def test_due_reminder_is_notified(captured_events):
    events, bus, db = captured_events
    service.create_reminder(db, text="llamar al médico", due_at=datetime.now() - timedelta(minutes=1))

    assert ReminderScheduler(bus).check_due() == 1
    assert len(events) == 1
    assert events[0].type is EventType.NOTIFICATION_CREATED
    assert events[0].payload["reminder"] == "llamar al médico"


def test_future_reminder_is_not_notified(captured_events):
    events, bus, db = captured_events
    service.create_reminder(db, text="mañana", due_at=datetime.now() + timedelta(hours=2))

    assert ReminderScheduler(bus).check_due() == 0
    assert events == []


def test_reminder_is_notified_only_once(captured_events):
    """Sin la marca, el scheduler avisaría cada 30 segundos para siempre."""
    events, bus, db = captured_events
    service.create_reminder(db, text="una sola vez", due_at=datetime.now() - timedelta(minutes=1))
    scheduler = ReminderScheduler(bus)

    assert scheduler.check_due() == 1
    assert scheduler.check_due() == 0  # segunda pasada: ya avisado
    assert len(events) == 1


def test_completed_reminders_are_skipped(captured_events):
    """Si ya lo diste por hecho, no tiene sentido que suene."""
    events, bus, db = captured_events
    created = service.create_reminder(db, text="hecho", due_at=datetime.now() - timedelta(minutes=5))
    service.mark_done(db, created.id)

    assert ReminderScheduler(bus).check_due() == 0
    assert events == []


def test_several_due_reminders_all_notify(captured_events):
    events, bus, db = captured_events
    for i in range(3):
        service.create_reminder(db, text=f"tarea {i}", due_at=datetime.now() - timedelta(minutes=i + 1))

    assert ReminderScheduler(bus).check_due() == 3
    assert len(events) == 3


def test_notified_flag_is_persisted(captured_events):
    """Se marca en la base, no en memoria: si no, reiniciar el backend
    volvería a avisar todo lo vencido."""
    _, bus, db = captured_events
    service.create_reminder(db, text="persistir", due_at=datetime.now() - timedelta(minutes=1))
    ReminderScheduler(bus).check_due()

    assert db.query(Reminder).first().notified is True


def test_notification_message_is_readable(db_session):
    """El texto que ve el usuario, no el payload crudo."""
    from app.notifications.service import _format_message

    event = Event(
        type=EventType.NOTIFICATION_CREATED,
        payload={"reminder": "sacar la basura", "due_at": "2026-08-27T18:00:00"},
    )
    assert _format_message(event) == "Recordatorio: sacar la basura"


def test_late_column_migration_runs(db_session):
    """La columna `notified` se agregó después de que la base ya existía;
    create_all no toca tablas existentes, así que hay un parche en init_db."""
    from app.core.database import _LATE_COLUMNS

    assert ("reminders", "notified", "BOOLEAN NOT NULL DEFAULT 0") in _LATE_COLUMNS
