"""Seguir objetos, marcas en el mapa e imágenes (show_world_view / query_world)."""
from __future__ import annotations

from app.tools.base import ToolContext
from app.tools.world.query_world import QueryWorldTool
from app.tools.world.show_world_view import ShowWorldViewTool
from app.world.client import GodsEyeClient, GodsEyeResult
from app.world.state import WorldViewState

VIEW = {"camera": {"lat": -34.6, "lon": -58.4, "altitude_m": 30000}, "layers": [], "annotations": []}
PNG = "iVBORw0KGgo="


class RoutedClient:
    """Responde según la tool pedida; `handlers` mapea nombre -> función(arguments) -> GodsEyeResult."""

    def __init__(self, **handlers) -> None:
        self._handlers = handlers
        self.calls: list[tuple[str, dict]] = []

    def call_tool(self, name: str, arguments: dict) -> GodsEyeResult:
        self.calls.append((name, arguments))
        return self._handlers[name](arguments)


def _show(arguments: dict) -> GodsEyeResult:
    """Simula el geocodificador: cada lugar cae en coordenadas distintas."""
    place = (arguments.get("area") or {}).get("place", "")
    camera = {"lat": float(len(place)), "lon": -float(len(place)), "altitude_m": 1000}
    return GodsEyeResult(summary=f"Open {place}", data={"url": "http://x", "view": {**VIEW, "camera": camera}})


def _final_call(client: RoutedClient) -> dict:
    return client.calls[-1][1]


# ---------- seguir ----------


def test_follow_aircraft_resolves_callsign_to_its_id(db_session):
    client = RoutedClient(
        find_aircraft=lambda a: GodsEyeResult(
            "", {"rows": [{"id": "e064cb", "callsign": "ARG1676", "lat": -34.5, "lon": -58.3}]}
        ),
        show_in_gods_eye_view=_show,
    )
    state = WorldViewState()

    result = ShowWorldViewTool(client, state).execute(
        {"follow_aircraft": "arg 1676", "cockpit": True}, ToolContext(db=db_session)
    )

    assert result.success
    assert "siguiendo al avión ARG1676" in result.data
    assert client.calls[0] == ("find_aircraft", {"callsign": "ARG1676", "limit": 1})
    # Sin lugar pedido, se encuadra donde está el avión (Gods Eye View exige un encuadre).
    assert _final_call(client) == {
        "follow": {"kind": "aircraft", "id": "e064cb", "cockpit": True},
        "area": {"lat": -34.5, "lon": -58.3, "radius_km": 100},
    }
    assert state.latest() is not None


def test_follow_aircraft_tries_icao_then_callsign_then_registration(db_session):
    client = RoutedClient(find_aircraft=lambda a: GodsEyeResult("", {"rows": []}), show_in_gods_eye_view=_show)
    state = WorldViewState()

    result = ShowWorldViewTool(client, state).execute({"follow_aircraft": "e064cb"}, ToolContext(db=db_session))

    assert not result.success
    assert "No encontré ningún avión" in result.error
    assert [list(args)[0] for _, args in client.calls] == ["icao24", "callsign", "registration"]
    assert state.latest() is None


def test_follow_satellite_by_alias_number_and_name(db_session):
    client = RoutedClient(
        next_satellite_pass=lambda a: GodsEyeResult("", {"norad": 20580, "satellite": "HST"}),
        show_in_gods_eye_view=_show,
    )
    tool = ShowWorldViewTool(client, WorldViewState())
    context = ToolContext(db=db_session)

    whole_earth = {"lat": 0, "lon": 0, "altitude_m": 20_000_000}

    tool.execute({"follow_satellite": "ISS"}, context)
    assert _final_call(client) == {"follow": {"kind": "satellite", "id": "25544"}, "camera": whole_earth}

    tool.execute({"follow_satellite": "48274", "place": "Madrid"}, context)
    assert _final_call(client) == {"follow": {"kind": "satellite", "id": "48274"}, "area": {"place": "Madrid"}}

    result = tool.execute({"follow_satellite": "Hubble"}, context)
    assert _final_call(client)["follow"] == {"kind": "satellite", "id": "20580"}
    assert "siguiendo a HST" in result.data


# ---------- marcas ----------


def test_place_marks_are_sent_by_name(db_session):
    client = RoutedClient(show_in_gods_eye_view=_show)
    marks = [
        {"type": "pin", "place": "Obelisco", "label": "Acá", "color": "red"},
        {"type": "area", "place": "Palermo", "color": "fucsia"},
    ]

    result = ShowWorldViewTool(client, WorldViewState()).execute(
        {"place": "Buenos Aires", "marks": marks}, ToolContext(db=db_session)
    )

    assert result.success
    assert len(client.calls) == 1  # no hace falta geocodificar
    assert _final_call(client)["annotations"] == [
        {"type": "pin", "label": "Acá", "color": "red", "target": "Obelisco"},
        {"type": "area", "target": "Palermo"},  # un color inválido se descarta
    ]


def test_route_and_arrow_resolve_each_place_to_coordinates(db_session):
    client = RoutedClient(show_in_gods_eye_view=_show)
    marks = [
        {"type": "route", "places": ["Roma", "Milan", "Turin"]},
        {"type": "arrow", "places": ["Roma", "Paris"], "label": "Vuelo"},
    ]

    ShowWorldViewTool(client, WorldViewState()).execute({"marks": marks}, ToolContext(db=db_session))

    # Sin lugar pedido, se encuadra el rectángulo que ocupan los puntos, con margen.
    assert _final_call(client)["area"] == {"bbox": [-5.5, 3.5, -3.5, 5.5]}
    route, arrow = _final_call(client)["annotations"]
    assert route == {
        "type": "route",
        "points": [
            {"latitude": 4.0, "longitude": -4.0},
            {"latitude": 5.0, "longitude": -5.0},
            {"latitude": 5.0, "longitude": -5.0},
        ],
    }
    assert arrow == {
        "type": "arrow",
        "label": "Vuelo",
        "latitude": 4.0,
        "longitude": -4.0,
        "toLatitude": 5.0,
        "toLongitude": -5.0,
    }


def test_invalid_marks_are_rejected_before_showing_anything(db_session):
    client = RoutedClient(show_in_gods_eye_view=_show)
    tool = ShowWorldViewTool(client, WorldViewState())
    context = ToolContext(db=db_session)

    for marks in (
        [{"type": "pin"}],
        [{"type": "arrow", "places": ["Roma"]}],
        [{"type": "route", "places": ["Roma"]}],
        [{"type": "garabato", "place": "Roma"}],
    ):
        assert not tool.execute({"marks": marks}, context).success
    assert client.calls == []


# ---------- imágenes y clima ----------


def test_weather_returns_only_the_weather_section(db_session):
    sections = {
        "weather": {"summary": "Weather at Madrid: clear, 21°C.", "data": {"weather": {"temperature_c": 21}}},
        "aircraft": {"summary": "40 aircraft", "data": {"rows": [{"callsign": "IBE1"}]}},
    }
    client = RoutedClient(situation_brief=lambda a: GodsEyeResult("Situation", {"sections": sections}))

    result = QueryWorldTool(client, WorldViewState()).execute(
        {"topic": "weather", "place": "Madrid"}, ToolContext(db=db_session)
    )

    assert result.success
    assert result.data.startswith("Weather at Madrid: clear, 21°C.")
    assert "IBE1" not in result.data


def test_satellite_image_is_returned_for_the_chat(db_session):
    client = RoutedClient(
        get_weather_map=lambda a: GodsEyeResult("Global satellite", {"view": VIEW}, [("image/png", PNG)])
    )
    state = WorldViewState()

    result = QueryWorldTool(client, state).execute({"topic": "satellite_image"}, ToolContext(db=db_session))

    assert result.success
    assert client.calls == [("get_weather_map", {"map": "global_satellite"})]
    assert [(i.mime_type, i.data) for i in result.images] == [("image/png", PNG)]
    assert PNG not in result.data  # la imagen no va al modelo
    assert state.latest() is not None


def test_image_topics_fail_clearly_without_an_image(db_session):
    client = RoutedClient(get_weather_map=lambda a: GodsEyeResult("Radar", {}))
    result = QueryWorldTool(client, WorldViewState()).execute(
        {"topic": "radar_image", "place": "Florida"}, ToolContext(db=db_session)
    )
    assert not result.success


def test_camera_image_takes_the_nearest_camera(db_session):
    client = RoutedClient(
        find_cctv_cameras=lambda a: GodsEyeResult("1 camera", {"rows": [{"id": "cam-7", "name": "Puente"}]}),
        get_cctv_snapshot=lambda a: GodsEyeResult("", {}, [("image/jpeg", PNG)]),
    )

    result = QueryWorldTool(client, WorldViewState()).execute(
        {"topic": "camera_image", "place": "Austin"}, ToolContext(db=db_session)
    )

    assert result.success
    assert client.calls[1] == ("get_cctv_snapshot", {"camera_id": "cam-7"})
    assert result.data.startswith("Cámara Puente")
    assert result.images[0].mime_type == "image/jpeg"


def test_camera_image_reports_when_there_are_no_cameras(db_session):
    client = RoutedClient(find_cctv_cameras=lambda a: GodsEyeResult("The catalog has no cameras there.", {"rows": []}))
    result = QueryWorldTool(client, WorldViewState()).execute(
        {"topic": "camera_image", "place": "Nueva York"}, ToolContext(db=db_session)
    )
    assert not result.success
    assert "no cameras" in result.error


def test_earthquake_minimum_magnitude_is_forwarded(db_session):
    client = RoutedClient(get_earthquakes=lambda a: GodsEyeResult("3 earthquakes", {}))
    QueryWorldTool(client, WorldViewState()).execute(
        {"topic": "earthquakes", "min_magnitude": 6}, ToolContext(db=db_session)
    )
    assert client.calls == [("get_earthquakes", {"limit": 5, "min_magnitude": 6.0})]


def test_client_collects_images_from_the_mcp_result(monkeypatch):
    import requests

    class Response:
        def raise_for_status(self) -> None:
            pass

        def json(self) -> dict:
            content = [{"type": "text", "text": "Radar"}, {"type": "image", "mimeType": "image/png", "data": PNG}]
            return {"result": {"content": content, "structuredContent": {"map": "radar"}}}

    monkeypatch.setattr(requests, "post", lambda *args, **kwargs: Response())

    result = GodsEyeClient("http://127.0.0.1:4173").call_tool("get_weather_map", {"map": "radar"})

    assert result.images == [("image/png", PNG)]


def test_chat_response_carries_tool_images(client, auth_headers, monkeypatch):
    def fake_call_tool(self, name, arguments):
        return GodsEyeResult("Global satellite", {"view": VIEW}, [("image/png", PNG)])

    monkeypatch.setattr(GodsEyeClient, "call_tool", fake_call_tool)

    body = client.post(
        "/api/v1/chat", json={"message": "mostrame la imagen satelital"}, headers=auth_headers
    ).json()

    assert body["images"] == [{"mime_type": "image/png", "data": PNG}]
    assert "Global satellite" in body["reply"]


def test_place_marks_alone_frame_the_first_marked_place(db_session):
    client = RoutedClient(show_in_gods_eye_view=_show)

    ShowWorldViewTool(client, WorldViewState()).execute(
        {"marks": [{"type": "pin", "place": "Obelisco"}]}, ToolContext(db=db_session)
    )

    assert _final_call(client)["area"] == {"place": "Obelisco"}


def test_layers_alone_show_the_whole_earth(db_session):
    client = RoutedClient(show_in_gods_eye_view=_show)

    ShowWorldViewTool(client, WorldViewState()).execute({"layers": ["earthquakes"]}, ToolContext(db=db_session))

    assert _final_call(client) == {
        "layers": ["earthquakes"],
        "camera": {"lat": 0, "lon": 0, "altitude_m": 20_000_000},
    }
