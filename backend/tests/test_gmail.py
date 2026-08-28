"""Tests de Gmail (Fase 23). Mismo criterio que test_google_calendar.py:
mockean `requests`, no pegan a la API real ni dependen de credenciales.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from app.integrations.gmail import GmailClient, GmailError, GmailNotConfigured
from app.tools.base import ToolContext
from app.tools.gmail.list_unread_emails import ListUnreadEmailsTool
from app.tools.gmail.send_email import SendEmailTool


def _mock_response(json_data, status_code=200):
    response = MagicMock()
    response.status_code = status_code
    response.json.return_value = json_data
    response.text = str(json_data)
    return response


def _client(client_id="id", client_secret="secret", refresh_token="refresh"):
    return GmailClient(client_id, client_secret, refresh_token)


# ---------- Autenticación ----------


def test_list_unread_requires_credentials():
    client = _client(client_id="", client_secret="", refresh_token="")
    with pytest.raises(GmailNotConfigured):
        client.list_unread()


def test_refresh_failure_raises_gmail_error():
    token_response = _mock_response({"error": "invalid_grant"}, status_code=400)
    client = _client()
    with patch("requests.post", return_value=token_response):
        with pytest.raises(GmailError):
            client.list_unread()


# ---------- list_unread ----------


def test_list_unread_returns_parsed_summaries():
    token_response = _mock_response({"access_token": "fake-token", "expires_in": 3600})
    list_response = _mock_response({"messages": [{"id": "msg1", "threadId": "t1"}]})
    detail_response = _mock_response(
        {
            "id": "msg1",
            "snippet": "Hola, ¿cómo estás?",
            "payload": {"headers": [{"name": "Subject", "value": "Saludo"}, {"name": "From", "value": "a@b.com"}]},
        }
    )

    client = _client()
    with patch("requests.post", return_value=token_response), patch(
        "requests.get", side_effect=[list_response, detail_response]
    ):
        emails = client.list_unread()

    assert len(emails) == 1
    assert emails[0].subject == "Saludo"
    assert emails[0].sender == "a@b.com"
    assert emails[0].snippet == "Hola, ¿cómo estás?"


def test_list_unread_returns_empty_when_no_messages():
    token_response = _mock_response({"access_token": "fake-token", "expires_in": 3600})
    list_response = _mock_response({})

    client = _client()
    with patch("requests.post", return_value=token_response), patch("requests.get", return_value=list_response):
        emails = client.list_unread()

    assert emails == []


def test_list_unread_emails_tool_reports_missing_credentials(db_session):
    client = _client(client_id="", client_secret="", refresh_token="")
    result = ListUnreadEmailsTool(client).execute({}, ToolContext(db=db_session))
    assert not result.success
    assert "google_calendar_setup" in result.error


# ---------- send ----------


def test_send_posts_base64_mime_message():
    token_response = _mock_response({"access_token": "fake-token", "expires_in": 3600})
    send_response = _mock_response({"id": "sent1"})

    client = _client()
    with patch("requests.post", side_effect=[token_response, send_response]) as post_mock:
        message_id = client.send(to="dest@example.com", subject="Hola", body="Cuerpo del mensaje")

    assert message_id == "sent1"
    send_call = post_mock.call_args_list[1]
    assert "raw" in send_call.kwargs["json"]


def test_send_email_tool_reports_missing_params(db_session):
    result = SendEmailTool(_client()).execute({"to": "", "subject": "", "body": ""}, ToolContext(db=db_session))
    assert not result.success


def test_send_email_tool_surfaces_api_error(db_session):
    token_response = _mock_response({"access_token": "fake-token", "expires_in": 3600})
    error_response = _mock_response({"error": "boom"}, status_code=500)

    client = _client()
    with patch("requests.post", side_effect=[token_response, error_response]):
        result = SendEmailTool(client).execute(
            {"to": "x@example.com", "subject": "Asunto", "body": "Cuerpo"}, ToolContext(db=db_session)
        )

    assert not result.success
    assert "500" in result.error


def test_send_email_tool_is_medium_risk():
    from app.security.permissions import RiskLevel

    assert SendEmailTool(_client()).risk_level == RiskLevel.MEDIUM_RISK
