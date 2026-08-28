"""Tests de Google Calendar (Fase 21). Mismo criterio que
test_integrations.py: mockean `requests`, no pegan a la API real ni
dependen de tener credenciales configuradas.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from app.integrations.google_calendar import (
    GoogleCalendarClient,
    GoogleCalendarError,
    GoogleCalendarNotConfigured,
)
from app.tools.base import ToolContext
from app.tools.calendar.create_event import CreateCalendarEventTool
from app.tools.calendar.list_events import ListCalendarEventsTool


def _mock_response(json_data, status_code=200):
    response = MagicMock()
    response.status_code = status_code
    response.json.return_value = json_data
    response.text = str(json_data)
    return response


def _client(client_id="id", client_secret="secret", refresh_token="refresh"):
    return GoogleCalendarClient(client_id, client_secret, refresh_token, "primary")


# ---------- Autenticación ----------


def test_list_events_requires_credentials():
    client = _client(client_id="", client_secret="", refresh_token="")
    with pytest.raises(GoogleCalendarNotConfigured):
        client.list_events("2026-08-28T00:00:00-03:00", "2026-08-29T00:00:00-03:00")


def test_reuses_cached_access_token():
    token_response = _mock_response({"access_token": "fake-token", "expires_in": 3600})
    events_response = _mock_response({"items": []})

    client = _client()
    with patch("requests.post", return_value=token_response) as post_mock, patch(
        "requests.get", return_value=events_response
    ):
        client.list_events("2026-08-28T00:00:00-03:00", "2026-08-29T00:00:00-03:00")
        client.list_events("2026-08-29T00:00:00-03:00", "2026-08-30T00:00:00-03:00")

    post_mock.assert_called_once()  # segunda llamada reusa el token cacheado


def test_refresh_failure_raises_calendar_error():
    token_response = _mock_response({"error": "invalid_grant"}, status_code=400)

    client = _client()
    with patch("requests.post", return_value=token_response):
        with pytest.raises(GoogleCalendarError):
            client.list_events("2026-08-28T00:00:00-03:00", "2026-08-29T00:00:00-03:00")


# ---------- list_events ----------


def test_list_events_returns_parsed_events():
    token_response = _mock_response({"access_token": "fake-token", "expires_in": 3600})
    events_response = _mock_response(
        {
            "items": [
                {
                    "id": "evt1",
                    "summary": "Reunión",
                    "start": {"dateTime": "2026-08-28T10:00:00-03:00"},
                    "end": {"dateTime": "2026-08-28T11:00:00-03:00"},
                    "htmlLink": "https://calendar.google.com/evt1",
                }
            ]
        }
    )

    client = _client()
    with patch("requests.post", return_value=token_response), patch(
        "requests.get", return_value=events_response
    ):
        events = client.list_events("2026-08-28T00:00:00-03:00", "2026-08-29T00:00:00-03:00")

    assert len(events) == 1
    assert events[0].summary == "Reunión"
    assert events[0].start == "2026-08-28T10:00:00-03:00"


def test_list_events_tool_reports_missing_params(db_session):
    result = ListCalendarEventsTool(_client()).execute(
        {"time_min": "", "time_max": ""}, ToolContext(db=db_session)
    )
    assert not result.success


def test_list_events_tool_reports_missing_credentials(db_session):
    client = _client(client_id="", client_secret="", refresh_token="")
    result = ListCalendarEventsTool(client).execute(
        {"time_min": "2026-08-28T00:00:00-03:00", "time_max": "2026-08-29T00:00:00-03:00"},
        ToolContext(db=db_session),
    )
    assert not result.success
    assert "google_calendar_setup" in result.error


# ---------- create_event ----------


def test_create_event_posts_expected_payload():
    token_response = _mock_response({"access_token": "fake-token", "expires_in": 3600})
    created_response = _mock_response(
        {
            "id": "evt2",
            "summary": "Dentista",
            "start": {"dateTime": "2026-08-29T15:00:00-03:00"},
            "end": {"dateTime": "2026-08-29T16:00:00-03:00"},
        }
    )

    client = _client()
    with patch("requests.post", side_effect=[token_response, created_response]) as post_mock:
        event = client.create_event(
            summary="Dentista", start="2026-08-29T15:00:00-03:00", end="2026-08-29T16:00:00-03:00"
        )

    assert event.summary == "Dentista"
    create_call = post_mock.call_args_list[1]
    assert create_call.kwargs["json"]["summary"] == "Dentista"


def test_create_event_tool_reports_missing_params(db_session):
    result = CreateCalendarEventTool(_client()).execute(
        {"summary": "", "start": "", "end": ""}, ToolContext(db=db_session)
    )
    assert not result.success


def test_create_event_tool_surfaces_api_error(db_session):
    token_response = _mock_response({"access_token": "fake-token", "expires_in": 3600})
    error_response = _mock_response({"error": "boom"}, status_code=500)

    client = _client()
    with patch("requests.post", side_effect=[token_response, error_response]):
        result = CreateCalendarEventTool(client).execute(
            {"summary": "X", "start": "2026-08-29T15:00:00-03:00", "end": "2026-08-29T16:00:00-03:00"},
            ToolContext(db=db_session),
        )

    assert not result.success
    assert "500" in result.error
