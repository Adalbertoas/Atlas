"""Cliente de Gmail vía la misma cuenta OAuth2 que Google Calendar
(GOOGLE_CLIENT_ID/GOOGLE_CLIENT_SECRET/GOOGLE_REFRESH_TOKEN) — un usuario,
una sola cuenta de Google, un solo consentimiento. El refresh_token tiene
que incluir el scope de Gmail además del de Calendar: si se generó antes de
esta fase, hay que volver a correr scripts/google_calendar_setup.py.

Mismo criterio de simplicidad que google_calendar.py: `requests` puro, sin
el SDK oficial. Repite el patrón de refresco de token de
GoogleCalendarClient en vez de compartir una clase base — mismo criterio
que SpotifyClient/AuddClient en este proyecto: cada integración es pequeña
y autocontenida, compartir una base agregaría una capa de indirección para
ahorrar ~15 líneas.
"""
from __future__ import annotations

import base64
import time
from dataclasses import dataclass
from email.mime.text import MIMEText

import requests

_TIMEOUT = 10
_TOKEN_URL = "https://oauth2.googleapis.com/token"
_API_BASE = "https://gmail.googleapis.com/gmail/v1/users/me"

# readonly: listar/leer. send: mandar — a propósito NO se pide
# gmail.modify/gmail.full: no hace falta borrar ni archivar correo para lo
# que hacen las tools, y pedir menos de lo necesario es más fácil de
# justificar en la pantalla de consentimiento.
SCOPE = "https://www.googleapis.com/auth/gmail.readonly https://www.googleapis.com/auth/gmail.send"


class GmailNotConfigured(Exception):
    """Faltan GOOGLE_CLIENT_ID/GOOGLE_CLIENT_SECRET/GOOGLE_REFRESH_TOKEN, o el
    refresh_token no incluye el scope de Gmail (se generó antes de esta fase)."""


class GmailError(Exception):
    """Gmail respondió con un error — se propaga tal cual."""


@dataclass
class EmailSummary:
    id: str
    subject: str
    sender: str
    snippet: str


class GmailClient:
    def __init__(self, client_id: str, client_secret: str, refresh_token: str) -> None:
        self._client_id = client_id
        self._client_secret = client_secret
        self._refresh_token = refresh_token
        self._access_token: str | None = None
        self._token_expires_at: float = 0.0

    def _get_access_token(self) -> str:
        if not self._client_id or not self._client_secret or not self._refresh_token:
            raise GmailNotConfigured(
                "Falta configurar Gmail. Corré 'python scripts/google_calendar_setup.py' "
                "(incluye el scope de Gmail) y completá GOOGLE_CLIENT_ID, "
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
            raise GmailError(
                f"No se pudo renovar el acceso a Gmail ({response.status_code}): {response.text}."
            )
        payload = response.json()
        self._access_token = payload["access_token"]
        self._token_expires_at = time.monotonic() + payload.get("expires_in", 3600) - 60
        return self._access_token

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self._get_access_token()}"}

    def list_unread(self, max_results: int = 5) -> list[EmailSummary]:
        list_response = requests.get(
            f"{_API_BASE}/messages",
            headers=self._headers(),
            params={"q": "is:unread", "maxResults": max_results},
            timeout=_TIMEOUT,
        )
        if list_response.status_code != 200:
            raise GmailError(f"Gmail respondió {list_response.status_code}: {list_response.text}")

        message_ids = [item["id"] for item in list_response.json().get("messages", [])]
        summaries = []
        for message_id in message_ids:
            detail_response = requests.get(
                f"{_API_BASE}/messages/{message_id}",
                headers=self._headers(),
                params={"format": "metadata", "metadataHeaders": ["Subject", "From"]},
                timeout=_TIMEOUT,
            )
            if detail_response.status_code != 200:
                raise GmailError(f"Gmail respondió {detail_response.status_code}: {detail_response.text}")
            summaries.append(_to_summary(detail_response.json()))
        return summaries

    def send(self, to: str, subject: str, body: str) -> str:
        """Devuelve el id del mensaje enviado."""
        mime_message = MIMEText(body)
        mime_message["to"] = to
        mime_message["subject"] = subject
        raw = base64.urlsafe_b64encode(mime_message.as_bytes()).decode("ascii")

        response = requests.post(
            f"{_API_BASE}/messages/send",
            headers=self._headers(),
            json={"raw": raw},
            timeout=_TIMEOUT,
        )
        if response.status_code not in (200, 202):
            raise GmailError(f"Gmail respondió {response.status_code}: {response.text}")
        return response.json().get("id", "")


def _to_summary(message: dict) -> EmailSummary:
    headers = {h["name"]: h["value"] for h in message.get("payload", {}).get("headers", [])}
    return EmailSummary(
        id=message.get("id", ""),
        subject=headers.get("Subject", "(sin asunto)"),
        sender=headers.get("From", "(remitente desconocido)"),
        snippet=message.get("snippet", ""),
    )
