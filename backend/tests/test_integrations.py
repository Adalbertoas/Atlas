"""Tests de las integraciones externas (Fase 10): Wikipedia, clima
(Open-Meteo), YouTube y Spotify. Todos mockean `requests` — no pegan a
las APIs reales (evita flakiness de red y no depende de tener API keys).
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from app.integrations.audd import AuddError, AuddNotConfigured, identify_song
from app.integrations.spotify import SpotifyClient, SpotifyNotConfigured
from app.integrations.weather import get_weather
from app.integrations.wikipedia import search_wikipedia
from app.integrations.youtube import YouTubeNotConfigured, search_youtube
from app.tools.base import ToolContext
from app.tools.knowledge.search_wikipedia import SearchWikipediaTool
from app.tools.music.search_spotify import SearchSpotifyTool
from app.tools.music.search_youtube import SearchYouTubeTool
from app.tools.weather.get_weather import GetWeatherTool


def _mock_response(json_data, status_code=200):
    response = MagicMock()
    response.status_code = status_code
    response.json.return_value = json_data
    response.raise_for_status = MagicMock()
    if status_code >= 400:
        response.raise_for_status.side_effect = Exception(f"HTTP {status_code}")
    return response


# ---------- Wikipedia ----------


def test_search_wikipedia_returns_summary():
    opensearch_response = _mock_response(["torre eiffel", ["Torre Eiffel"], [""], ["https://es.wikipedia.org/wiki/Torre_Eiffel"]])
    summary_response = _mock_response({"title": "Torre Eiffel", "extract": "Una torre en París."})

    with patch("requests.get", side_effect=[opensearch_response, summary_response]):
        result = search_wikipedia("torre eiffel")

    assert result.title == "Torre Eiffel"
    assert "torre en París" in result.summary


def test_search_wikipedia_returns_none_when_no_results():
    opensearch_response = _mock_response(["asdasdasd", [], [], []])

    with patch("requests.get", return_value=opensearch_response):
        result = search_wikipedia("asdasdasd")

    assert result is None


def test_search_wikipedia_tool_reports_no_results(db_session):
    with patch("app.tools.knowledge.search_wikipedia.search_wikipedia", return_value=None):
        result = SearchWikipediaTool().execute({"query": "algo inexistente"}, ToolContext(db=db_session))

    assert result.success
    assert "No encontré" in result.data


# ---------- Clima ----------


def test_get_weather_returns_current_conditions():
    geocoding_response = _mock_response({"results": [{"name": "Buenos Aires", "latitude": -34.6, "longitude": -58.4}]})
    forecast_response = _mock_response(
        {
            "current": {
                "temperature_2m": 22.5,
                "apparent_temperature": 21.0,
                "relative_humidity_2m": 60,
                "wind_speed_10m": 10.0,
                "weather_code": 1,
            }
        }
    )

    with patch("requests.get", side_effect=[geocoding_response, forecast_response]):
        result = get_weather("Buenos Aires")

    assert result.city == "Buenos Aires"
    assert result.temperature_c == 22.5
    assert result.description == "mayormente despejado"


def test_get_weather_returns_none_when_city_not_found():
    geocoding_response = _mock_response({"results": []})

    with patch("requests.get", return_value=geocoding_response):
        result = get_weather("ciudad-inventada-xyz")

    assert result is None


def test_get_weather_tool_reports_missing_city(db_session):
    result = GetWeatherTool().execute({"city": ""}, ToolContext(db=db_session))
    assert not result.success


# ---------- YouTube ----------


def test_search_youtube_requires_api_key():
    with pytest.raises(YouTubeNotConfigured):
        search_youtube("python tutorial", api_key="")


def test_search_youtube_returns_videos():
    response = _mock_response(
        {
            "items": [
                {
                    "id": {"videoId": "abc123"},
                    "snippet": {"title": "Tutorial", "channelTitle": "Canal", "publishedAt": "2026-01-01"},
                }
            ]
        }
    )

    with patch("requests.get", return_value=response):
        videos = search_youtube("python tutorial", api_key="fake-key")

    assert len(videos) == 1
    assert videos[0].url == "https://www.youtube.com/watch?v=abc123"


def test_search_youtube_skips_channel_results():
    # Visto en vivo: buscar "Bruno Mars" trae su canal oficial primero
    # (id.kind="youtube#channel", sin videoId) a pesar de pedir type="video"
    # — rompía con KeyError. Debe saltearlo y devolver solo los videos.
    response = _mock_response(
        {
            "items": [
                {
                    "id": {"kind": "youtube#channel", "channelId": "chan1"},
                    "snippet": {"title": "Bruno Mars", "channelTitle": "Bruno Mars", "publishedAt": "2006-01-01"},
                },
                {
                    "id": {"kind": "youtube#video", "videoId": "abc123"},
                    "snippet": {"title": "Tutorial", "channelTitle": "Canal", "publishedAt": "2026-01-01"},
                },
            ]
        }
    )

    with patch("requests.get", return_value=response):
        videos = search_youtube("Bruno Mars", api_key="fake-key")

    assert len(videos) == 1
    assert videos[0].url == "https://www.youtube.com/watch?v=abc123"


def test_search_youtube_tool_reports_missing_key(db_session):
    result = SearchYouTubeTool(api_key="").execute({"query": "algo"}, ToolContext(db=db_session))
    assert not result.success
    assert "YOUTUBE_API_KEY" in result.error


# ---------- Spotify ----------


def test_spotify_search_requires_credentials():
    client = SpotifyClient(client_id="", client_secret="")
    with pytest.raises(SpotifyNotConfigured):
        client.search_track("algo")


def test_spotify_search_returns_tracks():
    token_response = _mock_response({"access_token": "fake-token", "expires_in": 3600})
    search_response = _mock_response(
        {
            "tracks": {
                "items": [
                    {
                        "name": "Cancion",
                        "artists": [{"name": "Artista"}],
                        "external_urls": {"spotify": "https://open.spotify.com/track/abc"},
                    }
                ]
            }
        }
    )

    client = SpotifyClient(client_id="id", client_secret="secret")
    with patch("requests.post", return_value=token_response), patch("requests.get", return_value=search_response):
        tracks = client.search_track("cancion")

    assert len(tracks) == 1
    assert tracks[0].name == "Cancion"
    assert tracks[0].artists == "Artista"


def test_spotify_search_reuses_cached_token():
    token_response = _mock_response({"access_token": "fake-token", "expires_in": 3600})
    search_response = _mock_response({"tracks": {"items": []}})

    client = SpotifyClient(client_id="id", client_secret="secret")
    with patch("requests.post", return_value=token_response) as post_mock, patch(
        "requests.get", return_value=search_response
    ):
        client.search_track("a")
        client.search_track("b")

    post_mock.assert_called_once()  # segunda búsqueda reusa el token cacheado


def test_search_spotify_tool_reports_missing_credentials(db_session):
    client = SpotifyClient(client_id="", client_secret="")
    result = SearchSpotifyTool(client).execute({"query": "algo"}, ToolContext(db=db_session))
    assert not result.success
    assert "SPOTIFY_CLIENT_ID" in result.error


# ---------- AudD (Shazam) ----------


def test_identify_song_requires_api_token():
    with pytest.raises(AuddNotConfigured):
        identify_song(b"fake-audio-bytes", api_token="")


def test_identify_song_returns_match():
    response = _mock_response(
        {
            "status": "success",
            "result": {
                "artist": "Queen",
                "title": "Bohemian Rhapsody",
                "album": "A Night at the Opera",
                "song_link": "https://lis.tn/BohemianRhapsody",
            },
        }
    )

    with patch("requests.post", return_value=response):
        match = identify_song(b"fake-audio-bytes", api_token="fake-token")

    assert match.artist == "Queen"
    assert match.title == "Bohemian Rhapsody"


def test_identify_song_extracts_spotify_cover_and_link():
    """AudD se pide con `return: spotify` — hasta que esto se agregó, esa
    metadata se descartaba entera salvo por song_link (el smart-link propio
    de AudD, que no trae ninguna miniatura asociada)."""
    response = _mock_response(
        {
            "status": "success",
            "result": {
                "artist": "Queen",
                "title": "Bohemian Rhapsody",
                "album": "A Night at the Opera",
                "song_link": "https://lis.tn/BohemianRhapsody",
                "spotify": {
                    "external_urls": {"spotify": "https://open.spotify.com/track/abc123"},
                    "album": {
                        "images": [
                            {"url": "https://i.scdn.co/image/large.jpg", "height": 640, "width": 640},
                            {"url": "https://i.scdn.co/image/small.jpg", "height": 64, "width": 64},
                        ]
                    },
                },
            },
        }
    )

    with patch("requests.post", return_value=response):
        match = identify_song(b"fake-audio-bytes", api_token="fake-token")

    assert match.cover_url == "https://i.scdn.co/image/large.jpg"
    assert match.track_url == "https://open.spotify.com/track/abc123"


def test_identify_song_falls_back_to_apple_music_when_no_spotify_match():
    """Caso real encontrado en vivo: "Siempre Estoy Pensando en Ella" de
    Gramatiko no tuvo match en el catálogo de Spotify de AudD, pero sí en el
    de Apple Music — sin este fallback, la tarjeta se quedaba sin miniatura
    aunque AudD sí tenía una portada para ofrecer."""
    response = _mock_response(
        {
            "status": "success",
            "result": {
                "artist": "Gramatiko",
                "title": "Siempre Estoy Pensando en Ella",
                "album": "Siempre Estoy Pensando en Ella",
                "song_link": "https://lis.tn/MVTCb",
                "apple_music": {
                    "url": "https://music.apple.com/us/album/siempre-estoy-pensando-en-ella/123",
                    "artwork": {
                        "url": "https://is2-ssl.mzstatic.com/image/thumb/abc/{w}x{h}bb.jpeg",
                        "width": 3000,
                        "height": 3000,
                    },
                },
            },
        }
    )

    with patch("requests.post", return_value=response):
        match = identify_song(b"fake-audio-bytes", api_token="fake-token")

    assert match.cover_url == "https://is2-ssl.mzstatic.com/image/thumb/abc/600x600bb.jpeg"
    assert match.track_url == "https://music.apple.com/us/album/siempre-estoy-pensando-en-ella/123"


def test_identify_song_prefers_spotify_over_apple_music_when_both_present():
    response = _mock_response(
        {
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
                "apple_music": {
                    "url": "https://music.apple.com/us/album/x/1",
                    "artwork": {"url": "https://is2-ssl.mzstatic.com/x/{w}x{h}bb.jpeg"},
                },
            },
        }
    )

    with patch("requests.post", return_value=response):
        match = identify_song(b"fake-audio-bytes", api_token="fake-token")

    assert match.cover_url == "https://i.scdn.co/image/large.jpg"
    assert match.track_url == "https://open.spotify.com/track/abc123"


def test_identify_song_handles_missing_spotify_metadata():
    """No toda canción reconocida por huella de audio está en el catálogo de
    Spotify NI en el de Apple Music (temas muy nuevos o poco distribuidos) —
    sin ninguno de los dos bloques, el match se sigue devolviendo igual,
    solo que sin portada."""
    response = _mock_response(
        {
            "status": "success",
            "result": {"artist": "Alguien", "title": "Tema raro", "album": None, "song_link": None},
        }
    )

    with patch("requests.post", return_value=response):
        match = identify_song(b"fake-audio-bytes", api_token="fake-token")

    assert match.cover_url is None
    assert match.track_url is None


def test_identify_song_returns_none_when_no_match():
    response = _mock_response({"status": "success", "result": None})

    with patch("requests.post", return_value=response):
        match = identify_song(b"fake-audio-bytes", api_token="fake-token")

    assert match is None


def test_identify_song_raises_on_api_error():
    response = _mock_response({"status": "error", "error": {"error_code": 901, "error_message": "boom"}})

    with patch("requests.post", return_value=response):
        with pytest.raises(AuddError, match="boom"):
            identify_song(b"fake-audio-bytes", api_token="fake-token")


def test_unfingerprintable_audio_is_not_an_error():
    """AudD usa error_code 300 cuando no pudo generar la huella (silencio,
    clip muy corto, puro ruido). Eso es "no reconocí nada", no una falla:
    propagarlo como excepción producía un 500 — y como FastAPI no le agrega
    cabeceras CORS a un 500 sin manejar, el navegador lo reportaba como un
    error de CORS, escondiendo el motivo real."""
    response = _mock_response(
        {"status": "error", "error": {"error_code": 300, "error_message": "fingerprint failed"}}
    )

    with patch("requests.post", return_value=response):
        assert identify_song(b"fake-audio-bytes", api_token="fake-token") is None


def test_identify_endpoint_maps_audd_error_to_502(client, auth_headers, monkeypatch):
    """El fallo es del servicio externo, no de ATLAS."""
    from app.config import get_settings

    monkeypatch.setenv("AUDD_API_TOKEN", "fake-token")
    get_settings.cache_clear()

    response = _mock_response({"status": "error", "error": {"error_code": 901, "error_message": "boom"}})
    with patch("requests.post", return_value=response):
        result = client.post(
            "/api/v1/music/identify",
            files={"audio": ("clip.wav", b"fake-audio-bytes", "audio/wav")},
            headers=auth_headers,
        )

    get_settings.cache_clear()
    assert result.status_code == 502
    assert "boom" in result.json()["detail"]
