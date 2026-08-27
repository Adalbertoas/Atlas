"""Cliente de AudD (https://audd.io) — reconocimiento de canciones a partir
de un fragmento de audio grabado (equivalente a Shazam). Elegido en vez de
`shazamio` porque esa librería depende de un componente en Rust
(`shazamio-core`) que no tiene wheel prebuilt para Python 3.13 en Windows y
falló al compilar en esta máquina (toolchain de Rust/MSVC roto acá) — ver
docs/architecture.md. AudD es una API REST simple, sin nada que compilar.

Necesita AUDD_API_TOKEN (cuenta gratis en audd.io, sin tarjeta).
"""
from __future__ import annotations

from dataclasses import dataclass

import requests

_TIMEOUT = 15  # más que el resto: sube un archivo de audio, no solo un query corto


class AuddNotConfigured(Exception):
    """AUDD_API_TOKEN vacío — falta configurar .env."""


class AuddError(Exception):
    """AudD respondió con un error propio (siempre con HTTP 200)."""


# AudD usa este código cuando no pudo generar una huella del audio: pasa con
# clips en silencio, demasiado cortos, o con puro ruido. No es una falla del
# servidor — es el resultado normal de "no reconocí nada", así que se trata
# como tal en vez de propagarlo como error.
FINGERPRINT_FAILED_CODE = 300


@dataclass
class SongMatch:
    artist: str
    title: str
    album: str | None
    song_link: str | None


def identify_song(audio_bytes: bytes, api_token: str) -> SongMatch | None:
    """None si no se reconoció ninguna canción en el fragmento."""
    if not api_token:
        raise AuddNotConfigured(
            "AUDD_API_TOKEN vacío. Creá una cuenta gratis en https://audd.io (sin tarjeta), "
            "copiá tu API token desde el dashboard y ponelo en backend/.env."
        )

    response = requests.post(
        "https://api.audd.io/",
        data={"api_token": api_token, "return": "spotify"},
        files={"file": ("audio.wav", audio_bytes)},
        timeout=_TIMEOUT,
    )
    response.raise_for_status()
    payload = response.json()

    if payload.get("status") != "success":
        error = payload.get("error") or {}
        if error.get("error_code") == FINGERPRINT_FAILED_CODE:
            return None  # audio inservible: es "no reconocí nada", no una falla
        raise AuddError(
            f"AudD devolvió un error: {error.get('error_message') or payload} "
            f"(code {error.get('error_code')})"
        )

    result = payload.get("result")
    if not result:
        return None

    return SongMatch(
        artist=result["artist"],
        title=result["title"],
        album=result.get("album"),
        song_link=result.get("song_link"),
    )
