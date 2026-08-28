"""Cliente de Google Calendar vía OAuth2 "instalada" (loopback), mismo
criterio de simplicidad que el resto de app/integrations/: `requests` puro,
sin el SDK oficial (`google-api-python-client`), que arrastra varias
dependencias solo para hacer llamadas REST simples — el mismo motivo por el
que home_assistant_provider.py usa requests directo en vez de un cliente
generado.

Necesita GOOGLE_CLIENT_ID/GOOGLE_CLIENT_SECRET/GOOGLE_REFRESH_TOKEN — se
consiguen corriendo `scripts/google_calendar_setup.py` una sola vez.
"""
from __future__ import annotations

import time
from dataclasses import dataclass

import requests

_TIMEOUT = 10
_TOKEN_URL = "https://oauth2.googleapis.com/token"
_API_BASE = "https://www.googleapis.com/calendar/v3"

# Alcance mínimo: leer y crear eventos. No pide acceso a la lista de
# calendarios ni a compartir/borrar — lo que la tool no necesita, no se pide.
SCOPE = "https://www.googleapis.com/auth/calendar.events"


class GoogleCalendarNotConfigured(Exception):
    """Faltan GOOGLE_CLIENT_ID/GOOGLE_CLIENT_SECRET/GOOGLE_REFRESH_TOKEN en .env."""


class GoogleCalendarError(Exception):
    """Google respondió con un error (token inválido/revocado, calendario
    inexistente, etc.) — se propaga tal cual en vez de fingir éxito."""


@dataclass
class CalendarEvent:
    id: str
    summary: str
    start: str  # ISO 8601 (dateTime) o "YYYY-MM-DD" (evento de día completo)
    end: str
    description: str
    html_link: str


class GoogleCalendarClient:
    """Cachea el access_token en memoria del proceso (dura ~1h — pedirlo en
    cada llamada sería un round-trip extra inútil), igual que SpotifyClient."""

    def __init__(self, client_id: str, client_secret: str, refresh_token: str, calendar_id: str) -> None:
        self._client_id = client_id
        self._client_secret = client_secret
        self._refresh_token = refresh_token
        self._calendar_id = calendar_id or "primary"
        self._access_token: str | None = None
        self._token_expires_at: float = 0.0

    def _get_access_token(self) -> str:
        if not self._client_id or not self._client_secret or not self._refresh_token:
            raise GoogleCalendarNotConfigured(
                "Falta configurar Google Calendar. Corré "
                "'python scripts/google_calendar_setup.py' y completá GOOGLE_CLIENT_ID, "
                "GOOGLE_CLIENT_SECRET y GOOGLE_REFRESH_TOKEN en backend/.env."
            )
        if self._access_token and time.monotonic() < self._token_expires_at:
            return self._access_token

        response = requests.post(
            _TOKEN_URL,
            data={
                "client_id": self._client_id,
                "client_secret": self._client_secret,
                "refresh_token": self._refresh_token,
                "grant_type": "refresh_token",
            },
            timeout=_TIMEOUT,
        )
        if response.status_code != 200:
            raise GoogleCalendarError(
                f"No se pudo renovar el acceso a Google Calendar ({response.status_code}): "
                f"{response.text}. Si el refresh token fue revocado, hay que repetir "
                "scripts/google_calendar_setup.py."
            )
        payload = response.json()
        self._access_token = payload["access_token"]
        # Margen de 60s para no arrancar una llamada con un token que vence
        # a mitad de la request.
        self._token_expires_at = time.monotonic() + payload.get("expires_in", 3600) - 60
        return self._access_token

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self._get_access_token()}"}

    def list_events(self, time_min: str, time_max: str, max_results: int = 10) -> list[CalendarEvent]:
        response = requests.get(
            f"{_API_BASE}/calendars/{self._calendar_id}/events",
            headers=self._headers(),
            params={
                "timeMin": time_min,
                "timeMax": time_max,
                "singleEvents": "true",
                "orderBy": "startTime",
                "maxResults": max_results,
            },
            timeout=_TIMEOUT,
        )
        if response.status_code != 200:
            raise GoogleCalendarError(f"Google Calendar respondió {response.status_code}: {response.text}")

        items = response.json().get("items", [])
        return [_to_event(item) for item in items]

    def create_event(self, summary: str, start: str, end: str, description: str = "") -> CalendarEvent:
        response = requests.post(
            f"{_API_BASE}/calendars/{self._calendar_id}/events",
            headers=self._headers(),
            json={
                "summary": summary,
                "description": description,
                "start": {"dateTime": start},
                "end": {"dateTime": end},
            },
            timeout=_TIMEOUT,
        )
        if response.status_code not in (200, 201):
            raise GoogleCalendarError(f"Google Calendar respondió {response.status_code}: {response.text}")

        return _to_event(response.json())


def _to_event(item: dict) -> CalendarEvent:
    start = item.get("start", {})
    end = item.get("end", {})
    return CalendarEvent(
        id=item.get("id", ""),
        summary=item.get("summary", "(sin título)"),
        start=start.get("dateTime") or start.get("date", ""),
        end=end.get("dateTime") or end.get("date", ""),
        description=item.get("description", ""),
        html_link=item.get("htmlLink", ""),
    )
