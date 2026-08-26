from __future__ import annotations

from app.security.audit import list_recent, write_audit


def test_list_recent_returns_entries_newest_first(db_session):
    write_audit(
        db_session, tool_name="get_current_time", parameters={}, risk_level="READ_ONLY",
        result_summary="12:00", success=True,
    )
    write_audit(
        db_session, tool_name="open_application", parameters={"application_name": "notepad"},
        risk_level="MEDIUM_RISK", result_summary="abierto", success=True,
    )

    entries = list_recent(db_session)
    assert len(entries) == 2
    assert entries[0].tool_name == "open_application"  # el más reciente primero
    assert entries[1].tool_name == "get_current_time"


def test_list_recent_respects_limit(db_session):
    for i in range(5):
        write_audit(
            db_session, tool_name="get_current_time", parameters={}, risk_level="READ_ONLY",
            result_summary=str(i), success=True,
        )
    assert len(list_recent(db_session, limit=2)) == 2


def test_activity_endpoint_requires_auth(client):
    response = client.get("/api/v1/system/activity")
    assert response.status_code == 401


def test_activity_endpoint_returns_recent_tool_executions(client, auth_headers):
    # Genera actividad real ejecutando una tool vía chat (READ_ONLY, auto-ejecuta).
    client.post("/api/v1/chat", json={"message": "¿qué hora es?"}, headers=auth_headers)

    response = client.get("/api/v1/system/activity", headers=auth_headers)
    assert response.status_code == 200
    body = response.json()
    assert len(body) >= 1
    assert body[0]["tool_name"]
    assert "created_at" in body[0]
