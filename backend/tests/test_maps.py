"""Tests de mapas/rutas (Fase 24, OpenStreetMap: Nominatim + OSRM). Mismo
criterio que el resto: mockean `requests`, no pegan a los servidores
públicos reales.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

from app.integrations.maps import geocode, get_travel_time
from app.tools.base import ToolContext
from app.tools.maps.get_travel_time import GetTravelTimeTool


def _mock_response(json_data, status_code=200):
    response = MagicMock()
    response.status_code = status_code
    response.json.return_value = json_data
    response.raise_for_status = MagicMock()
    if status_code >= 400:
        response.raise_for_status.side_effect = Exception(f"HTTP {status_code}")
    return response


# ---------- geocode ----------


def test_geocode_returns_place():
    response = _mock_response(
        [{"display_name": "Santo Domingo, República Dominicana", "lat": "18.4861", "lon": "-69.9312"}]
    )
    with patch("requests.get", return_value=response):
        place = geocode("Santo Domingo")

    assert place.display_name == "Santo Domingo, República Dominicana"
    assert place.lat == 18.4861


def test_geocode_returns_none_when_not_found():
    response = _mock_response([])
    with patch("requests.get", return_value=response):
        assert geocode("lugar-inventado-xyz") is None


# ---------- get_travel_time ----------


def test_get_travel_time_returns_estimate():
    origin_response = _mock_response(
        [{"display_name": "Santo Domingo, RD", "lat": "18.4861", "lon": "-69.9312"}]
    )
    destination_response = _mock_response(
        [{"display_name": "Santiago, RD", "lat": "19.4517", "lon": "-70.6970"}]
    )
    route_response = _mock_response(
        {"code": "Ok", "routes": [{"distance": 155000, "duration": 7200}]}
    )

    with patch("requests.get", side_effect=[origin_response, destination_response, route_response]):
        estimate = get_travel_time("Santo Domingo", "Santiago")

    assert estimate.distance_km == 155.0
    assert estimate.duration_min == 120
    assert estimate.origin == "Santo Domingo, RD"


def test_get_travel_time_returns_none_when_origin_not_found():
    empty_response = _mock_response([])
    with patch("requests.get", return_value=empty_response):
        assert get_travel_time("lugar-inventado", "Santiago") is None


def test_get_travel_time_returns_none_when_no_route():
    origin_response = _mock_response([{"display_name": "A", "lat": "1", "lon": "1"}])
    destination_response = _mock_response([{"display_name": "B", "lat": "2", "lon": "2"}])
    no_route_response = _mock_response({"code": "NoRoute", "routes": []})

    with patch("requests.get", side_effect=[origin_response, destination_response, no_route_response]):
        assert get_travel_time("A", "B") is None


# ---------- tool ----------


def test_get_travel_time_tool_reports_missing_params(db_session):
    result = GetTravelTimeTool().execute({"origin": "", "destination": ""}, ToolContext(db=db_session))
    assert not result.success


def test_get_travel_time_tool_reports_no_route(db_session):
    with patch("app.tools.maps.get_travel_time.get_travel_time", return_value=None):
        result = GetTravelTimeTool().execute(
            {"origin": "A", "destination": "B"}, ToolContext(db=db_session)
        )
    assert result.success
    assert "No pude encontrar" in result.data


def test_get_travel_time_tool_formats_estimate(db_session):
    from app.integrations.maps import TravelEstimate

    estimate = TravelEstimate(origin="A", destination="B", distance_km=10.5, duration_min=15)
    with patch("app.tools.maps.get_travel_time.get_travel_time", return_value=estimate):
        result = GetTravelTimeTool().execute(
            {"origin": "A", "destination": "B"}, ToolContext(db=db_session)
        )

    assert result.success
    assert "10.5 km" in result.data
    assert "15 min" in result.data
