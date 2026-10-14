from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from app.briefing.service import BRIEFING_ROUTINE, build_briefing, ensure_briefing_routine
from app.automation import service as automation
from app.events.bus import EventBus, EventType
from app.memory.schemas import MemoryCreate
from app.memory.service import create_memory
from app.reminders import service as reminders
from app.tools.base import ToolContext
from app.tools.briefing.daily_briefing import DailyBriefingTool
from app.tools.reminders.reminder_tools import CancelReminderTool, CreateReminderTool, ListRemindersTool
from app.world.client import GodsEyeError, GodsEyeResult

# Martes 13 de octubre de 2026, 10:00 hora local.
NOW = datetime(2026, 10, 13, 10, 0, 0).astimezone()


def _collect(events: EventBus) -> list[str]:
    messages: list[str] = []
    events.subscribe(EventType.NOTIFICATION_CREATED, lambda event: messages.append(event.payload["message"]))
    return messages


# ---------- cuándo vence ----------


def test_resolve_due_in_seconds():
    assert reminders.resolve_due(NOW, in_seconds=90) == NOW + timedelta(seconds=90)


def test_resolve_due_time_today_or_tomorrow():
    assert reminders.resolve_due(NOW, at="18:30") == NOW.replace(hour=18, minute=30)
    # Las 9 ya pasaron: es mañana.
    assert reminders.resolve_due(NOW, at="09:00") == NOW.replace(hour=9) + timedelta(days=1)


def test_resolve_due_full_date_and_weekday():
    assert reminders.resolve_due(NOW, at="2026-12-24 20:00") == NOW.replace(month=12, day=24, hour=20)
    # Próximo lunes (el 13 es martes) a las 9.
    assert reminders.resolve_due(NOW, at="09:00", weekday="lunes") == NOW.replace(day=19, hour=9)
    # "martes a las 9" pedido un martes a las 10: el martes que viene.
    assert reminders.resolve_due(NOW, at="09:00", weekday="martes") == NOW.replace(day=20, hour=9)
    # "martes a las 18" pedido un martes a las 10: hoy mismo.
    assert reminders.resolve_due(NOW, at="18:00", weekday="tuesday") == NOW.replace(hour=18)


@pytest.mark.parametrize(
    "kwargs",
    [{}, {"in_seconds": 0}, {"at": "mañana"}, {"at": "2020-01-01 10:00"}, {"at": "09:00", "weekday": "feriado"}],
)
def test_resolve_due_rejects_what_it_cannot_understand(kwargs):
    with pytest.raises(ValueError):
        reminders.resolve_due(NOW, **kwargs)


# ---------- disparo ----------


def test_one_off_reminder_fires_once(db_session):
    events = EventBus()
    messages = _collect(events)
    reminders.create_reminder(db_session, "sacar la pizza", NOW + timedelta(minutes=20))
    now_utc = reminders.to_utc(NOW)

    assert reminders.fire_due(db_session, events, now_utc + timedelta(minutes=19)) == 0
    assert reminders.fire_due(db_session, events, now_utc + timedelta(minutes=20)) == 1
    assert reminders.fire_due(db_session, events, now_utc + timedelta(minutes=30)) == 0
    assert messages == ["⏰ Recordatorio: sacar la pizza"]
    assert reminders.list_pending(db_session) == []


def test_daily_reminder_moves_to_the_next_day_keeping_the_hour(db_session):
    due = NOW.replace(hour=9) + timedelta(days=1)
    reminder = reminders.create_reminder(db_session, "tomar la pastilla", due, repeat="daily")

    assert reminders.fire_due(db_session, EventBus(), reminders.to_utc(due)) == 1

    assert not reminder.done
    assert reminders.to_local(reminder.due_at) == due + timedelta(days=1)


def test_weekdays_reminder_skips_the_weekend(db_session):
    friday = NOW.replace(day=16, hour=8)
    reminder = reminders.create_reminder(db_session, "reunión", friday, repeat="weekdays")

    reminders.fire_due(db_session, EventBus(), reminders.to_utc(friday))

    assert reminders.to_local(reminder.due_at) == NOW.replace(day=19, hour=8)  # lunes


def test_overdue_weekly_reminder_jumps_past_now(db_session):
    """Si la PC estuvo apagada tres semanas, no se dispara tres veces seguidas."""
    due = NOW.replace(hour=9) + timedelta(days=1)
    reminder = reminders.create_reminder(db_session, "regar", due, repeat="weekly")
    events = EventBus()
    messages = _collect(events)
    later = reminders.to_utc(due + timedelta(days=20))

    assert reminders.fire_due(db_session, events, later) == 1
    assert reminders.fire_due(db_session, events, later) == 0
    assert len(messages) == 1
    assert reminders.to_local(reminder.due_at) == due + timedelta(days=21)


# ---------- tools y API ----------


def test_reminder_tools_create_list_and_cancel(db_session):
    context = ToolContext(db=db_session)

    created = CreateReminderTool().execute({"message": "llamar a mamá", "in_minutes": 20}, context)
    assert created.success
    assert "llamar a mamá" in created.data

    assert "id=1: llamar a mamá" in ListRemindersTool().execute({}, context).data
    assert not CreateReminderTool().execute({"message": "sin cuándo"}, context).success
    assert not CreateReminderTool().execute({"message": "", "in_minutes": 5}, context).success
    assert not CreateReminderTool().execute({"message": "x", "in_minutes": 5, "repeat": "nunca"}, context).success

    assert CancelReminderTool().execute({"reminder_id": 1}, context).success
    assert not CancelReminderTool().execute({"reminder_id": 1}, context).success
    assert "No hay recordatorios" in ListRemindersTool().execute({}, context).data


def test_reminders_api_lists_and_cancels(client, auth_headers, db_session):
    reminder = reminders.create_reminder(db_session, "regar", NOW + timedelta(days=400), repeat="weekly")

    body = client.get("/api/v1/reminders", headers=auth_headers).json()
    assert body[0]["message"] == "regar"
    assert "cada semana" in body[0]["description"]

    assert client.delete(f"/api/v1/reminders/{reminder.id}", headers=auth_headers).status_code == 200
    assert client.delete(f"/api/v1/reminders/{reminder.id}", headers=auth_headers).status_code == 404


def test_chat_creates_a_reminder_with_the_mock_provider(client, auth_headers, db_session):
    response = client.post(
        "/api/v1/chat", json={"message": "recordame sacar la pizza en 20 minutos"}, headers=auth_headers
    )

    assert "Recordatorio creado" in response.json()["reply"]
    (reminder,) = reminders.list_pending(db_session)
    assert reminder.message == "sacar la pizza"


# ---------- briefing ----------


class WeatherClient:
    def __init__(self, error: bool = False) -> None:
        self._error = error

    def call_tool(self, name: str, arguments: dict) -> GodsEyeResult:
        if self._error:
            raise GodsEyeError("Gods Eye View no responde")
        weather = {"weather_code": 2, "temperature_c": 17.9, "feels_like_c": 14.2, "wind_kph": 18.6}
        return GodsEyeResult(summary="", data={"sections": {"weather": {"data": {"weather": weather}}}})


def test_briefing_gathers_the_day(db_session):
    reminders.create_reminder(db_session, "dentista", NOW.replace(hour=16))
    reminders.create_reminder(db_session, "cumpleaños de Ana", NOW + timedelta(days=3))
    create_memory(db_session, MemoryCreate(content="Entrego el informe el viernes", category="project", tags=[]))
    automation.create_routine(
        db_session,
        automation.RoutineCreate(name="Modo Dormir", triggers=[{"type": "SCHEDULE", "config": {"time": "23:00"}}]),
    )

    text = build_briefing(db_session, WeatherClient(), "Buenos Aires", NOW)

    assert "Buen día. Hoy es martes 13 de octubre." in text
    assert "En Buenos Aires: parcialmente nublado, 18°C (sensación 14°C), viento de 19 km/h." in text
    assert "dentista (16:00)" in text
    assert "cumpleaños de Ana" not in text  # no es de hoy
    assert "Modo Dormir a las 23:00" in text
    assert "Entrego el informe el viernes" in text


def test_briefing_works_without_weather(db_session):
    for client in (None, WeatherClient(error=True)):
        text = build_briefing(db_session, client, "Buenos Aires", NOW)
        assert "Hoy es martes 13 de octubre." in text
        assert "En Buenos Aires" not in text
        assert "No tenés recordatorios para hoy." in text


def test_briefing_tool_can_deliver_as_notification(db_session):
    events = EventBus()
    messages = _collect(events)
    tool = DailyBriefingTool(None, "", events)

    assert tool.execute({}, ToolContext(db=db_session)).success
    assert messages == []
    result = tool.execute({"deliver": True}, ToolContext(db=db_session))
    assert messages == [f"☀️ {result.data}"]


def test_briefing_routine_follows_the_configured_time(db_session):
    ensure_briefing_routine(db_session, "08:00")
    ensure_briefing_routine(db_session, "07:30")  # cambiar la hora no duplica la rutina

    (routine,) = [r for r in automation.list_routines(db_session) if r.name == BRIEFING_ROUTINE]
    assert [t.config for t in routine.triggers] == [{"time": "07:30"}]
    assert [(a.tool_name, a.params) for a in routine.actions] == [("daily_briefing", {"deliver": True})]

    ensure_briefing_routine(db_session, "")
    assert automation.list_routines(db_session) == []

    with pytest.raises(ValueError):
        ensure_briefing_routine(db_session, "8 de la mañana")
