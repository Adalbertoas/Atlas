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
    # Portada real del álbum — sale de la metadata de Spotify que ya viene
    # en la respuesta (se pide con `return: spotify`), pero hasta ahora se
    # descartaba entera salvo por song_link. Sin esto, el link que se le
    # mostraba al usuario era el smart-link propio de AudD (lis.tn/...), que
    # no tiene ninguna miniatura asociada — ni el cliente puede armar una
    # sin pegarle a una API por su cuenta.
    cover_url: str | None = None
    # Link directo al track (Spotify o, si ese catálogo no tuvo match, Apple
    # Music) — más útil que song_link para armar una tarjeta: song_link es
    # un redirect "elegí tu plataforma" pensado para compartir, no para
    # enlazar directo. No se llama spotify_url porque puede no serlo.
    track_url: str | None = None


def identify_song(audio_bytes: bytes, api_token: str) -> SongMatch | None:
    """None si no se reconoció ninguna canción en el fragmento."""
    if not api_token:
        raise AuddNotConfigured(
            "AUDD_API_TOKEN vacío. Creá una cuenta gratis en https://audd.io (sin tarjeta), "
            "copiá tu API token desde el dashboard y ponelo en backend/.env."
        )

    response = requests.post(
        "https://api.audd.io/",
        # Se piden las dos fuentes a la vez: AudD reconoce la canción por su
        # huella de audio, independiente de en qué catálogos aparece
        # después — no es raro que un tema esté en uno y no en el otro
        # (visto en vivo: "Siempre Estoy Pensando en Ella" de Gramatiko no
        # tuvo match en Spotify pero sí en Apple Music). Pedir ambas cuesta
        # lo mismo que pedir una sola.
        data={"api_token": api_token, "return": "spotify,apple_music"},
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

    # La metadata de Spotify/Apple Music es opcional: AudD reconoce la
    # canción por su huella de audio, independiente de que después la
    # encuentre en uno, otro, ambos o ninguno de esos catálogos — en ese
    # caso el match se sigue devolviendo igual, solo que sin portada ni link
    # directo (el cliente cae al texto plano). Spotify primero por ser el
    # más usado; Apple Music como respaldo si Spotify no tuvo match.
    spotify = result.get("spotify") or {}
    album_images = ((spotify.get("album") or {}).get("images")) or []
    cover_url = album_images[0].get("url") if album_images else None
    link_url = (spotify.get("external_urls") or {}).get("spotify")

    if not cover_url or not link_url:
        apple_music = result.get("apple_music") or {}
        artwork_template = (apple_music.get("artwork") or {}).get("url")
        if not cover_url and artwork_template:
            # La URL de Apple Music viene con un template de tamaño
            # ("{w}x{h}bb.jpeg") en vez de una imagen fija — 600x600 es un
            # tamaño de portada estándar, ni el thumbnail más chico ni el
            # original a máxima resolución.
            cover_url = artwork_template.replace("{w}x{h}", "600x600")
        if not link_url:
            link_url = apple_music.get("url")

    return SongMatch(
        artist=result["artist"],
        title=result["title"],
        album=result.get("album"),
        song_link=result.get("song_link"),
        cover_url=cover_url,
        track_url=link_url,
    )
