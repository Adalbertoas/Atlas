from __future__ import annotations

from unittest.mock import MagicMock, patch

import requests


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
        "result": {
            "artist": "Queen",
            "title": "Bohemian Rhapsody",
            "album": None,
            "song_link": None,
            "spotify": {
                "external_urls": {"spotify": "https://open.spotify.com/track/abc123"},
                "album": {"images": [{"url": "https://i.scdn.co/image/large.jpg"}]},
            },
        },
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
    assert body["cover_url"] == "https://i.scdn.co/image/large.jpg"
    assert body["track_url"] == "https://open.spotify.com/track/abc123"


def test_identify_endpoint_falls_back_to_youtube_thumbnail(client, auth_headers, monkeypatch):
    """Ni Spotify ni Apple Music tuvieron match (caso real: música poco
    distribuida) — YouTube casi siempre tiene el tema, y su miniatura no
    necesita ninguna llamada extra, solo el video ID de la búsqueda."""
    from app.config import get_settings

    get_settings.cache_clear()
    monkeypatch.setenv("AUDD_API_TOKEN", "fake-token")
    monkeypatch.setenv("YOUTUBE_API_KEY", "fake-yt-key")
    get_settings.cache_clear()

    audd_response = MagicMock()
    audd_response.raise_for_status = MagicMock()
    audd_response.json.return_value = {
        "status": "success",
        "result": {"artist": "Gramatiko", "title": "Siempre Estoy Pensando en Ella", "album": None},
    }

    youtube_response = MagicMock()
    youtube_response.raise_for_status = MagicMock()
    youtube_response.json.return_value = {
        "items": [
            {
                "id": {"videoId": "abc123"},
                "snippet": {
                    "title": "Gramatiko - Siempre Estoy Pensando en Ella",
                    "channelTitle": "Gramatiko",
                    "publishedAt": "2020-01-01T00:00:00Z",
                },
            }
        ]
    }

    with patch("requests.post", return_value=audd_response), patch(
        "requests.get", return_value=youtube_response
    ):
        response = client.post(
            "/api/v1/music/identify",
            files={"audio": ("clip.wav", b"fake-audio-bytes", "audio/wav")},
            headers=auth_headers,
        )

    get_settings.cache_clear()
    body = response.json()
    assert body["cover_url"] == "https://img.youtube.com/vi/abc123/mqdefault.jpg"
    assert body["track_url"] == "https://www.youtube.com/watch?v=abc123"


def test_identify_endpoint_ignores_youtube_failures(client, auth_headers, monkeypatch):
    """El fallback a YouTube es best-effort: si falla, la identificación
    original (que sí funcionó) no debe caerse con ella."""
    from app.config import get_settings

    get_settings.cache_clear()
    monkeypatch.setenv("AUDD_API_TOKEN", "fake-token")
    monkeypatch.setenv("YOUTUBE_API_KEY", "fake-yt-key")
    get_settings.cache_clear()

    audd_response = MagicMock()
    audd_response.raise_for_status = MagicMock()
    audd_response.json.return_value = {
        "status": "success",
        "result": {"artist": "Alguien", "title": "Tema raro", "album": None},
    }

    with patch("requests.post", return_value=audd_response), patch(
        "requests.get", side_effect=requests.ConnectionError("sin red")
    ):
        response = client.post(
            "/api/v1/music/identify",
            files={"audio": ("clip.wav", b"fake-audio-bytes", "audio/wav")},
            headers=auth_headers,
        )

    get_settings.cache_clear()
    assert response.status_code == 200
    body = response.json()
    assert body["found"] is True
    assert body["cover_url"] is None
