"""Cliente de Spotify vía Client Credentials Flow (búsqueda pública,
sin login de usuario — necesita SPOTIFY_CLIENT_ID/SPOTIFY_CLIENT_SECRET,
gratis en developer.spotify.com: "Create app", cualquier Redirect URI
sirve porque este flujo no la usa).

Solo búsqueda: no controla reproducción (eso requeriría OAuth de usuario +
Spotify Premium + un dispositivo activo — fuera de alcance de esta fase).
"""
from __future__ import annotations

import base64
import time
from dataclasses import dataclass

import requests

_TIMEOUT = 10


class SpotifyNotConfigured(Exception):
    """SPOTIFY_CLIENT_ID/SECRET vacíos — falta configurar .env."""


@dataclass
class SpotifyTrack:
    name: str
    artists: str
    url: str


class SpotifyClient:
    """Cachea el access token en memoria del proceso (Client Credentials
    dura 1h — pedirlo en cada búsqueda sería un round-trip extra inútil)."""

    def __init__(self, client_id: str, client_secret: str) -> None:
        self._client_id = client_id
        self._client_secret = client_secret
        self._token: str | None = None
        self._token_expires_at: float = 0.0

    def _get_token(self) -> str:
        if not self._client_id or not self._client_secret:
            raise SpotifyNotConfigured(
                "SPOTIFY_CLIENT_ID/SPOTIFY_CLIENT_SECRET vacíos. Creá una app gratis en "
                "developer.spotify.com y ponelos en backend/.env."
            )
        if self._token and time.monotonic() < self._token_expires_at:
            return self._token

        credentials = base64.b64encode(f"{self._client_id}:{self._client_secret}".encode()).decode()
        response = requests.post(
            "https://accounts.spotify.com/api/token",
            headers={"Authorization": f"Basic {credentials}"},
            data={"grant_type": "client_credentials"},
            timeout=_TIMEOUT,
        )
        response.raise_for_status()
        payload = response.json()
        self._token = payload["access_token"]
        # -30s de margen para no usar un token que expira justo a mitad de un request.
        self._token_expires_at = time.monotonic() + payload["expires_in"] - 30
        return self._token

    def search_track(self, query: str, limit: int = 5) -> list[SpotifyTrack]:
        token = self._get_token()
        response = requests.get(
            "https://api.spotify.com/v1/search",
            headers={"Authorization": f"Bearer {token}"},
            params={"q": query, "type": "track", "limit": limit},
            timeout=_TIMEOUT,
        )
        response.raise_for_status()

        tracks = []
        for item in response.json().get("tracks", {}).get("items", []):
            tracks.append(
                SpotifyTrack(
                    name=item["name"],
                    artists=", ".join(a["name"] for a in item["artists"]),
                    url=item["external_urls"]["spotify"],
                )
            )
        return tracks
