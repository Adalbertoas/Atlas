from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from app.events.bus import EventBus, EventType
from app.tools.base import ToolContext
from app.tools.world.alerts import CreateWorldAlertTool, DeleteWorldAlertTool, ListWorldAlertsTool
from app.world import alerts
from app.world.client import GodsEyeError, GodsEyeResult

NOW = datetime(2026, 10, 13, 12, 0, 0)


class FakeClient:
    """Devuelve, en orden, los datos configurados para cada llamada."""

    def __init__(self, *responses) -> None:
        self._responses = list(responses)
        self.calls: list[tuple[str, dict]] = []

    def call_tool(self, name: str, arguments: dict) -> GodsEyeResult:
        self.calls.append((name, arguments))
        response = self._responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return GodsEyeResult(summary="", data=response)


def _collect(events: EventBus) -> list[str]:
    messages: list[str] = []
    events.subscribe(EventType.NOTIFICATION_CREATED, lambda event: messages.append(event.payload["message"]))
    return messages


def _quake(quake_id: str, magnitude: float, place: str) -> dict:
    return {"id": quake_id, "magnitude": magnitude, "place": place}


def test_first_check_is_a_baseline_and_later_ones_report_only_new_items(db_session):
    alert = alerts.create_alert(db_session, "earthquakes", place="Chile", min_magnitude=5)
    client = FakeClient(
        {"rows": [_quake("a", 5.2, "Valparaíso")]},
        {"rows": [_quake("a", 5.2, "Valparaíso"), _quake("b", 6.1, "Coquimbo")]},
        {"rows": [_quake("a", 5.2, "Valparaíso"), _quake("b", 6.1, "Coquimbo")]},
    )

    assert alerts.check_alert(alert, client, NOW) == []  # lo que ya había no se avisa
    messages = alerts.check_alert(alert, client, NOW)
    assert len(messages) == 1
    assert "M6.1 — Coquimbo" in messages[0]
    assert "Valparaíso" not in messages[0]
    assert alerts.check_alert(alert, client, NOW) == []  # ya avisado: no se repite

    assert client.calls[0] == (
        "get_earthquakes",
        {"area": {"place": "Chile"}, "limit": alerts.MAX_ROWS, "min_magnitude": 5.0},
    )


def test_many_new_items_are_summarized(db_session):
    alert = alerts.create_alert(db_session, "aircraft", place="Madrid")
    planes = [{"id": f"id{i}", "callsign": f"IBE{i}"} for i in range(6)]
    client = FakeClient({"rows": []}, {"rows": planes})

    alerts.check_alert(alert, client, NOW)
    (message,) = alerts.check_alert(alert, client, NOW)

    assert "IBE0" in message and "IBE2" in message
    assert "IBE3" not in message
    assert "y 3 más" in message


def test_cyclones_are_read_from_their_own_key(db_session):
    alert = alerts.create_alert(db_session, "cyclones")
    storm = {"id": "ep20", "name": "Simon", "classification": "HU", "wind_kt": 80}
    client = FakeClient({"storms": []}, {"storms": [storm]})

    alerts.check_alert(alert, client, NOW)
    (message,) = alerts.check_alert(alert, client, NOW)

    assert "Simon (HU, 80 kt)" in message
    assert "en todo el mundo" in message


def test_satellite_pass_notifies_once_when_the_pass_is_close(db_session):
    alert = alerts.create_alert(db_session, "satellite_pass", place="Buenos Aires")

    def data(rise: datetime) -> dict:
        return {
            "satellite": "ISS (ZARYA)",
            "pass": {
                "rise": rise.isoformat() + "Z",
                "rise_direction": "N",
                "max_elevation_deg": 25.4,
                "visible": True,
            },
        }

    far, near = NOW + timedelta(hours=3), NOW + timedelta(minutes=20)
    client = FakeClient(data(far), data(near), data(near))

    assert alerts.check_alert(alert, client, NOW) == []  # falta mucho
    (message,) = alerts.check_alert(alert, client, NOW)
    assert "ISS (ZARYA) pasa sobre Buenos Aires" in message
    assert "25°" in message and "visible a simple vista" in message
    assert alerts.check_alert(alert, client, NOW) == []  # misma pasada: no se repite
    assert client.calls[0] == ("next_satellite_pass", {"location": {"place": "Buenos Aires"}})


def test_service_errors_are_swallowed_and_retried_later(db_session):
    alert = alerts.create_alert(db_session, "ships", place="Montevideo")
    client = FakeClient(GodsEyeError("AISSTREAM_API_KEY not set"))

    assert alerts.check_alert(alert, client, NOW) == []
    assert alert.seen_json is None  # sigue pendiente la primera revisión real
    assert alert.last_checked_at == NOW


def test_check_due_alerts_respects_each_interval_and_notifies(db_session):
    alerts.create_alert(db_session, "earthquakes", interval_minutes=10)
    events = EventBus()
    messages = _collect(events)
    client = FakeClient({"rows": []}, {"rows": [_quake("x", 7.0, "Japón")]})

    assert alerts.check_due_alerts(db_session, client, events, NOW) == 0
    # A los 5 minutos todavía no toca: no se consulta.
    assert alerts.check_due_alerts(db_session, client, events, NOW + timedelta(minutes=5)) == 0
    assert len(client.calls) == 1
    assert alerts.check_due_alerts(db_session, client, events, NOW + timedelta(minutes=10)) == 1
    assert "M7.0 — Japón" in messages[0]


@pytest.mark.parametrize(
    ("topic", "place"),
    [("ovnis", "Madrid"), ("aircraft", ""), ("satellite_pass", ""), ("satellites", "Madrid")],
)
def test_create_alert_rejects_what_cannot_be_watched(db_session, topic, place):
    with pytest.raises(ValueError):
        alerts.create_alert(db_session, topic, place=place)


def test_alert_tools_create_list_and_delete(db_session):
    context = ToolContext(db=db_session)

    created = CreateWorldAlertTool().execute(
        {"topic": "earthquakes", "place": "Chile", "min_magnitude": 5, "every_minutes": 1}, context
    )
    assert created.success
    assert "terremotos de magnitud 5 o más en Chile" in created.data
    assert "cada 2 minutos" in created.data  # el mínimo es 2

    listed = ListWorldAlertsTool().execute({}, context)
    assert "id=1" in listed.data

    assert not CreateWorldAlertTool().execute({"topic": "aircraft"}, context).success
    assert DeleteWorldAlertTool().execute({"alert_id": 1}, context).success
    assert not DeleteWorldAlertTool().execute({"alert_id": 1}, context).success
    assert "No hay alertas" in ListWorldAlertsTool().execute({}, context).data


def test_alerts_api_lists_and_deletes(client, auth_headers, db_session):
    alert = alerts.create_alert(db_session, "launches")

    body = client.get("/api/v1/world/alerts", headers=auth_headers).json()
    assert body[0]["id"] == alert.id
    assert body[0]["description"] == "lanzamientos espaciales en todo el mundo"

    assert client.delete(f"/api/v1/world/alerts/{alert.id}", headers=auth_headers).status_code == 200
    assert client.delete(f"/api/v1/world/alerts/{alert.id}", headers=auth_headers).status_code == 404
