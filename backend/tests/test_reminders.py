from __future__ import annotations

from datetime import datetime, timedelta

from app.reminders import service
from app.tools.base import ToolContext
from app.tools.reminders.create_reminder import CreateReminderTool
from app.tools.reminders.list_reminders import ListRemindersTool


def _due(hours: int = 1) -> datetime:
    return datetime.now() + timedelta(hours=hours)


# ---------- service ----------


def test_create_and_list_reminder(db_session):
    service.create_reminder(db_session, text="llamar al médico", due_at=_due())
    reminders = service.list_reminders(db_session)

    assert len(reminders) == 1
    assert reminders[0].text == "llamar al médico"
    assert reminders[0].done is False


def test_list_reminders_orders_by_due_date_ascending(db_session):
    """El dashboard muestra "los próximos" — al revés que notificaciones,
    que van del más nuevo al más viejo."""
    service.create_reminder(db_session, text="más tarde", due_at=_due(5))
    service.create_reminder(db_session, text="primero", due_at=_due(1))

    reminders = service.list_reminders(db_session)
    assert [r.text for r in reminders] == ["primero", "más tarde"]


def test_pending_only_filters_out_completed(db_session):
    created = service.create_reminder(db_session, text="hecho", due_at=_due())
    service.create_reminder(db_session, text="pendiente", due_at=_due(2))
    service.mark_done(db_session, created.id)

    pending = service.list_reminders(db_session, pending_only=True)
    assert [r.text for r in pending] == ["pendiente"]
    assert len(service.list_reminders(db_session)) == 2


def test_mark_done_and_delete_return_false_when_missing(db_session):
    assert service.mark_done(db_session, 999) is False
    assert service.delete_reminder(db_session, 999) is False


def test_delete_reminder_removes_it(db_session):
    created = service.create_reminder(db_session, text="borrar", due_at=_due())
    assert service.delete_reminder(db_session, created.id) is True
    assert service.list_reminders(db_session) == []


# ---------- tools ----------


def test_create_reminder_tool_persists(db_session):
    tool = CreateReminderTool()
    result = tool.execute(
        {"text": "sacar la basura", "due_at": _due().isoformat()}, ToolContext(db=db_session)
    )

    assert result.success
    assert len(service.list_reminders(db_session)) == 1


def test_create_reminder_tool_rejects_bad_date(db_session):
    tool = CreateReminderTool()
    result = tool.execute({"text": "algo", "due_at": "mañana"}, ToolContext(db=db_session))

    assert not result.success
    assert "ISO 8601" in result.error


def test_create_reminder_tool_rejects_empty_text(db_session):
    tool = CreateReminderTool()
    result = tool.execute({"text": "  ", "due_at": _due().isoformat()}, ToolContext(db=db_session))
    assert not result.success


def test_list_reminders_tool_reports_when_empty(db_session):
    result = ListRemindersTool().execute({}, ToolContext(db=db_session))
    assert result.success
    assert "No hay recordatorios" in result.data


def test_list_reminders_tool_excludes_done_by_default(db_session):
    created = service.create_reminder(db_session, text="ya está", due_at=_due())
    service.mark_done(db_session, created.id)
    service.create_reminder(db_session, text="falta", due_at=_due(2))

    result = ListRemindersTool().execute({}, ToolContext(db=db_session))
    assert "falta" in result.data
    assert "ya está" not in result.data

    with_done = ListRemindersTool().execute({"include_done": True}, ToolContext(db=db_session))
    assert "ya está" in with_done.data


# ---------- API ----------


def test_reminders_api_create_list_and_complete(client, auth_headers):
    created = client.post(
        "/api/v1/reminders",
        json={"text": "comprar pan", "due_at": _due().isoformat()},
        headers=auth_headers,
    )
    assert created.status_code == 201
    reminder_id = created.json()["id"]

    listed = client.get("/api/v1/reminders", headers=auth_headers)
    assert listed.status_code == 200
    assert listed.json()[0]["text"] == "comprar pan"

    done = client.patch(f"/api/v1/reminders/{reminder_id}/done", headers=auth_headers)
    assert done.status_code == 200

    pending = client.get("/api/v1/reminders?pending_only=true", headers=auth_headers)
    assert pending.json() == []


def test_reminders_api_delete(client, auth_headers):
    created = client.post(
        "/api/v1/reminders",
        json={"text": "borrame", "due_at": _due().isoformat()},
        headers=auth_headers,
    )
    reminder_id = created.json()["id"]

    assert client.delete(f"/api/v1/reminders/{reminder_id}", headers=auth_headers).status_code == 204
    assert client.get("/api/v1/reminders", headers=auth_headers).json() == []


def test_reminders_api_404_on_missing(client, auth_headers):
    assert client.patch("/api/v1/reminders/999/done", headers=auth_headers).status_code == 404
    assert client.delete("/api/v1/reminders/999", headers=auth_headers).status_code == 404


def test_reminders_api_requires_auth(client):
    assert client.get("/api/v1/reminders").status_code == 401
