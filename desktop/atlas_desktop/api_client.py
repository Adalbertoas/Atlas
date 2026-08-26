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
