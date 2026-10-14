from __future__ import annotations

import requests

from app.tools.base import ToolContext
from app.tools.world.query_world import MAX_RESULT_CHARS, QueryWorldTool
from app.tools.world.show_world_view import ShowWorldViewTool
from app.world.client import GodsEyeClient, GodsEyeError, GodsEyeResult
from app.world.state import WorldViewState, world_view_state

VIEW = {
    "camera": {"lat": -34.6, "lon": -58.4, "altitude_m": 30000, "heading_deg": 0, "pitch_deg": -90},
    "layers": ["flights"],
    "style": None,
    "map": None,
    "follow": None,
    "annotations": [],
}
URL = "http://127.0.0.1:4173/#v=2"


class FakeClient:
    """Reemplaza a GodsEyeClient: registra la llamada y devuelve lo que se le configure."""

    def __init__(self, result: GodsEyeResult | None = None, error: str | None = None) -> None:
        self.calls: list[tuple[str, dict]] = []
        self._result = result
        self._error = error

    def call_tool(self, name: str, arguments: dict) -> GodsEyeResult:
        self.calls.append((name, arguments))
        if self._error:
            raise GodsEyeError(self._error)
        return self._result


class FakeResponse:
    def __init__(self, body: dict) -> None:
        self._body = body

    def raise_for_status(self) -> None:
        pass

    def json(self) -> dict:
        return self._body


# ---------- show_world_view ----------


def test_show_world_view_publishes_view_for_dashboard(db_session):
    client = FakeClient(GodsEyeResult(summary="Open Buenos Aires", data={"url": URL, "view": VIEW}))
    state = WorldViewState()
    tool = ShowWorldViewTool(client, state)

    result = tool.execute({"place": "Buenos Aires", "layers": ["flights", "ships"]}, ToolContext(db=db_session))

    assert result.success
    assert client.calls == [
        (
            "show_in_gods_eye_view",
            {"area": {"place": "Buenos Aires"}, "layers": ["flights", "ais-live-vessels"]},
        )
    ]
    update = state.latest()
    assert update.view == VIEW
    assert update.url == URL


def test_show_world_view_uses_coordinates_with_default_radius(db_session):
    client = FakeClient(GodsEyeResult(summary="", data={"url": URL, "view": VIEW}))
    tool = ShowWorldViewTool(client, WorldViewState())

    tool.execute({"lat": 40.4, "lon": -3.7}, ToolContext(db=db_session))

    assert client.calls[0][1] == {"area": {"lat": 40.4, "lon": -3.7, "radius_km": 50}}


def test_show_world_view_rejects_unknown_layer_without_calling(db_session):
    client = FakeClient()
    state = WorldViewState()
    tool = ShowWorldViewTool(client, state)

    result = tool.execute({"place": "Madrid", "layers": ["dragones"]}, ToolContext(db=db_session))

    assert not result.success
    assert "dragones" in result.error
    assert client.calls == []
    assert state.latest() is None


def test_show_world_view_requires_something_to_show(db_session):
    tool = ShowWorldViewTool(FakeClient(), WorldViewState())
    result = tool.execute({}, ToolContext(db=db_session))
    assert not result.success


def test_show_world_view_reports_service_down(db_session):
    state = WorldViewState()
    tool = ShowWorldViewTool(FakeClient(error="Gods Eye View no responde"), state)

    result = tool.execute({"place": "Madrid"}, ToolContext(db=db_session))

    assert not result.success
    assert "no responde" in result.error
    assert state.latest() is None


# ---------- query_world ----------


def test_query_world_maps_topic_and_returns_compact_rows(db_session):
    data = {
        "view": {**VIEW, "url": URL},
        "total": 6,
        "rows": [{"callsign": "ARG1676", "altitude_m": 549, "registration": None, "operator": None}],
    }
    client = FakeClient(GodsEyeResult(summary="6 aircraft in Buenos Aires.", data=data))
    state = WorldViewState()
    tool = QueryWorldTool(client, state)

    result = tool.execute({"topic": "military_aircraft", "place": "Buenos Aires"}, ToolContext(db=db_session))

    assert result.success
    assert client.calls == [
        ("aircraft_in_area", {"military": True, "area": {"place": "Buenos Aires"}, "limit": 5})
    ]
    assert result.data.startswith("6 aircraft in Buenos Aires.")
    assert "ARG1676" in result.data
    assert "registration" not in result.data  # los nulos no llegan al modelo
    assert '"view"' not in result.data
    # La vista se publica sin el link adentro: va aparte.
    update = state.latest()
    assert update.view == VIEW
    assert update.url == URL


def test_query_world_satellites_sends_place_as_location(db_session):
    client = FakeClient(GodsEyeResult(summary="ok", data={}))
    tool = QueryWorldTool(client, WorldViewState())

    tool.execute({"topic": "satellites", "place": "Madrid", "limit": 500}, ToolContext(db=db_session))

    assert client.calls == [("satellites_overhead", {"group": "visual", "location": {"place": "Madrid"}, "limit": 20})]


def test_query_world_earthquakes_work_without_place(db_session):
    client = FakeClient(GodsEyeResult(summary="45 earthquakes", data={}))
    tool = QueryWorldTool(client, WorldViewState())

    result = tool.execute({"topic": "earthquakes"}, ToolContext(db=db_session))

    assert result.success
    assert client.calls == [("get_earthquakes", {"limit": 5})]


def test_query_world_requires_place_for_area_topics(db_session):
    client = FakeClient()
    tool = QueryWorldTool(client, WorldViewState())

    result = tool.execute({"topic": "aircraft"}, ToolContext(db=db_session))

    assert not result.success
    assert client.calls == []


def test_query_world_rejects_unknown_topic(db_session):
    tool = QueryWorldTool(FakeClient(), WorldViewState())
    result = tool.execute({"topic": "ovnis"}, ToolContext(db=db_session))
    assert not result.success
    assert "ovnis" in result.error


def test_query_world_truncates_huge_results(db_session):
    data = {"rows": [{"name": "x" * 200} for _ in range(100)]}
    tool = QueryWorldTool(FakeClient(GodsEyeResult(summary="muchos", data=data)), WorldViewState())

    result = tool.execute({"topic": "launches"}, ToolContext(db=db_session))

    assert len(result.data) < MAX_RESULT_CHARS + 50
    assert result.data.endswith("(recortado)")


# ---------- cliente MCP ----------


def test_client_parses_mcp_tool_result(monkeypatch):
    sent = {}

    def fake_post(url, json, headers, timeout):
        sent.update(url=url, json=json)
        return FakeResponse(
            {
                "jsonrpc": "2.0",
                "id": 1,
                "result": {
                    "content": [{"type": "text", "text": "6 aircraft"}, {"type": "text", "text": "{}"}],
                    "structuredContent": {"total": 6},
                },
            }
        )

    monkeypatch.setattr(requests, "post", fake_post)
    result = GodsEyeClient("http://127.0.0.1:4173/").call_tool("aircraft_in_area", {"limit": 1})

    assert sent["url"] == "http://127.0.0.1:4173/mcp"
    assert sent["json"]["method"] == "tools/call"
    assert sent["json"]["params"] == {"name": "aircraft_in_area", "arguments": {"limit": 1}}
    assert result.summary == "6 aircraft"
    assert result.data == {"total": 6}


def test_client_raises_on_tool_error(monkeypatch):
    body = {
        "result": {
            "isError": True,
            "content": [{"type": "text", "text": 'No place matched "zzz"'}],
            "structuredContent": {"error": "invalid_arguments"},
        }
    }
    monkeypatch.setattr(requests, "post", lambda *a, **k: FakeResponse(body))

    try:
        GodsEyeClient("http://127.0.0.1:4173").call_tool("aircraft_in_area", {})
    except GodsEyeError as exc:
        assert "No place matched" in str(exc)
    else:
        raise AssertionError("se esperaba GodsEyeError")


def test_client_explains_when_service_is_down(monkeypatch):
    def refuse(*args, **kwargs):
        raise requests.ConnectionError("connection refused")

    monkeypatch.setattr(requests, "post", refuse)

    try:
        GodsEyeClient("http://127.0.0.1:4173").call_tool("get_earthquakes", {})
    except GodsEyeError as exc:
        assert "npm run dev" in str(exc)
    else:
        raise AssertionError("se esperaba GodsEyeError")


# ---------- API + flujo de chat ----------


def test_world_view_endpoint_requires_login(client):
    assert client.get("/api/v1/world/view").status_code in (401, 403)


def test_world_view_endpoint_returns_latest_view(client, auth_headers):
    update = world_view_state.publish(VIEW, URL, "Buenos Aires")

    body = client.get("/api/v1/world/view", headers=auth_headers).json()

    assert body == {"id": update.id, "view": VIEW, "url": URL, "summary": "Buenos Aires"}


def test_chat_question_about_flights_reaches_gods_eye(client, auth_headers, monkeypatch):
    """Flujo completo con el proveedor mock: chat -> query_world -> vista publicada."""
    data = {"view": {**VIEW, "url": URL}, "total": 6, "rows": []}
    calls = []

    def fake_call_tool(self, name, arguments):
        calls.append((name, arguments))
        return GodsEyeResult(summary="6 aircraft in Buenos Aires.", data=data)

    monkeypatch.setattr(GodsEyeClient, "call_tool", fake_call_tool)

    response = client.post(
        "/api/v1/chat", json={"message": "¿Qué vuelos hay ahora sobre Buenos Aires?"}, headers=auth_headers
    )

    assert calls == [("aircraft_in_area", {"area": {"place": "Buenos Aires"}, "limit": 5})]
    assert "6 aircraft in Buenos Aires." in response.json()["reply"]
    assert world_view_state.latest().view == VIEW
