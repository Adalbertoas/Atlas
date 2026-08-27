from __future__ import annotations

from dataclasses import dataclass, field

import pytest

from atlas_desktop import api_client


@dataclass
class FakeResponse:
    _json: dict = field(default_factory=dict)
    status_code: int = 200
    content: bytes = b""

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")

    def json(self) -> dict:
        return self._json


@pytest.fixture(autouse=True)
def _logged_in(monkeypatch):
    """La mayoría de las funciones de api_client ahora requieren estar
    logueado (Fase 7) — se simula una sesión activa por defecto; los tests
    de login/NotAuthenticatedError la desactivan explícitamente."""
    monkeypatch.setattr(api_client, "_token", "fake-token")


def test_login_stores_token(monkeypatch):
    monkeypatch.setattr(api_client, "_token", None)
    monkeypatch.setattr(
        api_client.requests, "post", lambda url, json=None, **kwargs: FakeResponse(_json={"access_token": "abc123"})
    )

    api_client.login("mi-contraseña")

    assert api_client.is_logged_in() is True


def test_calling_authenticated_endpoint_without_login_raises(monkeypatch):
    monkeypatch.setattr(api_client, "_token", None)
    with pytest.raises(api_client.NotAuthenticatedError):
        api_client.send_chat_message("hola", None)


def test_send_chat_message_posts_to_chat_endpoint_and_parses_reply(monkeypatch):
    captured = {}

    def fake_post(url, json=None, **kwargs):
        captured["url"] = url
        captured["json"] = json
        captured["headers"] = kwargs.get("headers")
        return FakeResponse(
            _json={
                "reply": "hola",
                "conversation_id": "conv-1",
                "requires_confirmation": False,
                "confirmation_id": None,
                "confirmation_description": None,
            }
        )

    monkeypatch.setattr(api_client.requests, "post", fake_post)

    result = api_client.send_chat_message("hola ATLAS", None)

    assert captured["url"].endswith("/api/v1/chat")
    assert captured["json"] == {"message": "hola ATLAS", "conversation_id": None}
    assert captured["headers"] == {"Authorization": "Bearer fake-token"}
    assert result.reply == "hola"
    assert result.conversation_id == "conv-1"
    assert result.requires_confirmation is False


def test_send_chat_message_parses_confirmation_fields(monkeypatch):
    monkeypatch.setattr(
        api_client.requests,
        "post",
        lambda url, json=None, **kwargs: FakeResponse(
            _json={
                "reply": None,
                "conversation_id": "conv-1",
                "requires_confirmation": True,
                "confirmation_id": "conf-1",
                "confirmation_description": "Abrir la calculadora",
            }
        ),
    )

    result = api_client.send_chat_message("abre la calculadora", "conv-1")

    assert result.requires_confirmation is True
    assert result.confirmation_id == "conf-1"
    assert result.confirmation_description == "Abrir la calculadora"


def test_confirm_action_posts_confirmation_id_and_approval(monkeypatch):
    captured = {}

    def fake_post(url, json=None, **kwargs):
        captured["url"] = url
        captured["json"] = json
        return FakeResponse(_json={"reply": "Listo."})

    monkeypatch.setattr(api_client.requests, "post", fake_post)

    reply = api_client.confirm_action("conf-1", True)

    assert captured["url"].endswith("/api/v1/chat/confirm")
    assert captured["json"] == {"confirmation_id": "conf-1", "approve": True}
    assert reply == "Listo."


def test_transcribe_audio_sends_multipart_file(monkeypatch):
    captured = {}

    def fake_post(url, files=None, **kwargs):
        captured["url"] = url
        captured["files"] = files
        return FakeResponse(_json={"text": "hola"})

    monkeypatch.setattr(api_client.requests, "post", fake_post)

    text = api_client.transcribe_audio(b"fake-wav-bytes")

    assert captured["url"].endswith("/api/v1/voice/transcribe")
    assert "audio" in captured["files"]
    assert text == "hola"


def test_identify_song_sends_multipart_file_and_parses_result(monkeypatch):
    captured = {}

    def fake_post(url, files=None, **kwargs):
        captured["url"] = url
        captured["files"] = files
        return FakeResponse(_json={"found": True, "artist": "Queen", "title": "Bohemian Rhapsody"})

    monkeypatch.setattr(api_client.requests, "post", fake_post)

    result = api_client.identify_song(b"fake-wav-bytes")

    assert captured["url"].endswith("/api/v1/music/identify")
    assert "audio" in captured["files"]
    assert result == {"found": True, "artist": "Queen", "title": "Bohemian Rhapsody"}


def test_synthesize_speech_returns_raw_audio_bytes(monkeypatch):
    monkeypatch.setattr(
        api_client.requests, "post", lambda url, json=None, **kwargs: FakeResponse(content=b"RIFF....")
    )
    audio = api_client.synthesize_speech("Hola")
    assert audio == b"RIFF...."


def test_get_system_status_returns_parsed_json(monkeypatch):
    monkeypatch.setattr(
        api_client.requests, "get", lambda url, **kwargs: FakeResponse(_json={"cpu_percent": 12.5})
    )
    status = api_client.get_system_status()
    assert status["cpu_percent"] == 12.5


def test_is_server_reachable_true_on_200(monkeypatch):
    monkeypatch.setattr(api_client.requests, "get", lambda url, **kwargs: FakeResponse(status_code=200))
    assert api_client.is_server_reachable() is True


def test_is_server_reachable_false_on_connection_error(monkeypatch):
    import requests

    def raise_connection_error(url, **kwargs):
        raise requests.RequestException("connection refused")

    monkeypatch.setattr(api_client.requests, "get", raise_connection_error)
    assert api_client.is_server_reachable() is False
