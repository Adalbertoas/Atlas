from __future__ import annotations

from unittest.mock import MagicMock, patch


def test_identify_endpoint_reports_missing_token(client, auth_headers):
    """En test no hay AUDD_API_TOKEN configurado — debe devolver 400
    explicativo en vez de un 500 genérico (ver app/api/v1/music.py)."""
    response = client.post(
        "/api/v1/music/identify",
        files={"audio": ("clip.wav", b"fake-audio-bytes", "audio/wav")},
        headers=auth_headers,
    )
    assert response.status_code == 400
    assert "AUDD_API_TOKEN" in response.json()["detail"]


def test_identify_endpoint_returns_match(client, auth_headers, monkeypatch):
    from app.config import get_settings

    get_settings.cache_clear()
    monkeypatch.setenv("AUDD_API_TOKEN", "fake-token")
    get_settings.cache_clear()

    audd_response = MagicMock()
    audd_response.raise_for_status = MagicMock()
    audd_response.json.return_value = {
        "status": "success",
        "result": {"artist": "Queen", "title": "Bohemian Rhapsody", "album": None, "song_link": None},
    }

    with patch("requests.post", return_value=audd_response):
        response = client.post(
            "/api/v1/music/identify",
            files={"audio": ("clip.wav", b"fake-audio-bytes", "audio/wav")},
            headers=auth_headers,
        )

    get_settings.cache_clear()  # no contaminar otros tests con esta env var
    assert response.status_code == 200
    body = response.json()
    assert body["found"] is True
    assert body["artist"] == "Queen"
