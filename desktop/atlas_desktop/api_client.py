"""Wrapper fino sobre la API HTTP de ATLAS.

Ninguna otra parte del cliente de escritorio debe llamar a `requests`
directamente — todo pasa por aquí, para que sea fácil de testear con un
`requests` simulado y para tener un único lugar que conozca los endpoints.

Fase 7: la API ahora exige login (antes el escritorio era anónimo). Este
módulo guarda el token en memoria de proceso tras login() y lo adjunta a
cada request autenticado.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import requests

from atlas_desktop.config import ATLAS_API_URL, ATLAS_CA_CERT

TIMEOUT_SECONDS = 60

_token: str | None = None


class NotAuthenticatedError(RuntimeError):
    pass


@dataclass
class ChatReply:
    reply: str | None
    conversation_id: str
    requires_confirmation: bool
    confirmation_id: str | None
    confirmation_description: str | None


def login(password: str) -> None:
    """Guarda el token en memoria de proceso para las siguientes llamadas."""
    global _token
    response = requests.post(
        f"{ATLAS_API_URL}/api/v1/auth/login", json={"password": password}, timeout=TIMEOUT_SECONDS, verify=ATLAS_CA_CERT
    )
    response.raise_for_status()
    _token = response.json()["access_token"]


def is_logged_in() -> bool:
    return _token is not None


def _auth_headers() -> dict:
    if _token is None:
        raise NotAuthenticatedError("No hay sesión activa: llamá a login() primero.")
    return {"Authorization": f"Bearer {_token}"}


def send_chat_message(message: str, conversation_id: str | None) -> ChatReply:
    response = requests.post(
        f"{ATLAS_API_URL}/api/v1/chat",
        json={"message": message, "conversation_id": conversation_id},
        headers=_auth_headers(),
        timeout=TIMEOUT_SECONDS,
        verify=ATLAS_CA_CERT,
    )
    response.raise_for_status()
    body = response.json()
    return ChatReply(
        reply=body.get("reply"),
        conversation_id=body["conversation_id"],
        requires_confirmation=body.get("requires_confirmation", False),
        confirmation_id=body.get("confirmation_id"),
        confirmation_description=body.get("confirmation_description"),
    )


def confirm_action(confirmation_id: str, approve: bool) -> str:
    response = requests.post(
        f"{ATLAS_API_URL}/api/v1/chat/confirm",
        json={"confirmation_id": confirmation_id, "approve": approve},
        headers=_auth_headers(),
        timeout=TIMEOUT_SECONDS,
        verify=ATLAS_CA_CERT,
    )
    response.raise_for_status()
    return response.json()["reply"]


def transcribe_audio(wav_bytes: bytes) -> str:
    response = requests.post(
        f"{ATLAS_API_URL}/api/v1/voice/transcribe",
        files={"audio": ("audio.wav", wav_bytes, "audio/wav")},
        headers=_auth_headers(),
        timeout=TIMEOUT_SECONDS,
        verify=ATLAS_CA_CERT,
    )
    response.raise_for_status()
    return response.json()["text"]


def synthesize_speech(text: str) -> bytes:
    response = requests.post(
        f"{ATLAS_API_URL}/api/v1/voice/speak",
        json={"text": text},
        headers=_auth_headers(),
        timeout=TIMEOUT_SECONDS,
        verify=ATLAS_CA_CERT,
    )
    response.raise_for_status()
    return response.content


def identify_song(wav_bytes: bytes) -> dict[str, Any]:
    """Fase 10: reconocimiento de canciones (tipo Shazam), vía AudD.
    Devuelve {"found": bool, "artist"?, "title"?, "album"?, "song_link"?}."""
    response = requests.post(
        f"{ATLAS_API_URL}/api/v1/music/identify",
        files={"audio": ("clip.wav", wav_bytes, "audio/wav")},
        headers=_auth_headers(),
        timeout=TIMEOUT_SECONDS,
        verify=ATLAS_CA_CERT,
    )
    response.raise_for_status()
    return response.json()


def _get(path: str, timeout: int = 15) -> Any:
    response = requests.get(
        f"{ATLAS_API_URL}{path}", headers=_auth_headers(), timeout=timeout, verify=ATLAS_CA_CERT
    )
    response.raise_for_status()
    return response.json()


# ---------- Lecturas para las vistas del cliente (Fase 15) ----------
# Envoltorios finos sobre los mismos endpoints que consume el dashboard, para
# que las dos interfaces muestren exactamente los mismos datos.


def get_profile() -> dict:
    return _get("/api/v1/settings/profile")


def list_devices() -> list[dict]:
    return _get("/api/v1/devices")


def list_automations() -> list[dict]:
    return _get("/api/v1/automations")


def run_routine(routine_id: int) -> dict:
    response = requests.post(
        f"{ATLAS_API_URL}/api/v1/automations/{routine_id}/run",
        headers=_auth_headers(),
        timeout=TIMEOUT_SECONDS,
        verify=ATLAS_CA_CERT,
    )
    response.raise_for_status()
    return response.json()


def list_reminders() -> list[dict]:
    return _get("/api/v1/reminders")


def create_reminder(text: str, due_at: str) -> dict:
    response = requests.post(
        f"{ATLAS_API_URL}/api/v1/reminders",
        json={"text": text, "due_at": due_at},
        headers=_auth_headers(),
        timeout=TIMEOUT_SECONDS,
        verify=ATLAS_CA_CERT,
    )
    response.raise_for_status()
    return response.json()


def complete_reminder(reminder_id: int) -> None:
    response = requests.patch(
        f"{ATLAS_API_URL}/api/v1/reminders/{reminder_id}/done",
        headers=_auth_headers(),
        timeout=TIMEOUT_SECONDS,
        verify=ATLAS_CA_CERT,
    )
    response.raise_for_status()


def delete_reminder(reminder_id: int) -> None:
    response = requests.delete(
        f"{ATLAS_API_URL}/api/v1/reminders/{reminder_id}",
        headers=_auth_headers(),
        timeout=TIMEOUT_SECONDS,
        verify=ATLAS_CA_CERT,
    )
    response.raise_for_status()


def list_memory() -> list[dict]:
    return _get("/api/v1/memory")


def delete_memory(memory_id: int) -> None:
    response = requests.delete(
        f"{ATLAS_API_URL}/api/v1/memory/{memory_id}",
        headers=_auth_headers(),
        timeout=TIMEOUT_SECONDS,
        verify=ATLAS_CA_CERT,
    )
    response.raise_for_status()


def list_notifications() -> list[dict]:
    return _get("/api/v1/notifications")


def mark_notification_read(notification_id: int) -> None:
    response = requests.patch(
        f"{ATLAS_API_URL}/api/v1/notifications/{notification_id}/read",
        headers=_auth_headers(),
        timeout=TIMEOUT_SECONDS,
        verify=ATLAS_CA_CERT,
    )
    response.raise_for_status()


def list_tools() -> list[dict]:
    return _get("/api/v1/tools")


def get_activity(limit: int = 30) -> list[dict]:
    return _get(f"/api/v1/system/activity?limit={limit}")


def get_gesture_status() -> dict:
    return _get("/api/v1/gestures/status")


def get_system_status() -> dict:
    response = requests.get(
        f"{ATLAS_API_URL}/api/v1/system/status", headers=_auth_headers(), timeout=10, verify=ATLAS_CA_CERT
    )
    response.raise_for_status()
    return response.json()


def is_server_reachable() -> bool:
    try:
        response = requests.get(f"{ATLAS_API_URL}/api/v1/system/health", timeout=3, verify=ATLAS_CA_CERT)
        return response.status_code == 200
    except requests.RequestException:
        return False
