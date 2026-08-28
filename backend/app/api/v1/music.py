from __future__ import annotations

import logging

import requests
from fastapi import APIRouter, HTTPException, UploadFile
from pydantic import BaseModel

from app.config import get_settings
from app.integrations.audd import AuddError, AuddNotConfigured, SongMatch, identify_song
from app.integrations.youtube import YouTubeNotConfigured, search_youtube

router = APIRouter(prefix="/music", tags=["music"])
logger = logging.getLogger(__name__)


class IdentifySongResponse(BaseModel):
    found: bool
    artist: str | None = None
    title: str | None = None
    album: str | None = None
    song_link: str | None = None
    cover_url: str | None = None
    track_url: str | None = None


def _fill_cover_from_youtube(match: SongMatch, youtube_api_key: str) -> SongMatch:
    """Tercera fuente de portada cuando ni Spotify ni Apple Music tuvieron
    match (AudD identifica por huella de audio, no por catálogo — puede
    reconocer un tema que no está en ninguno de los dos, sobre todo música
    poco distribuida). Un video de YouTube casi siempre existe, y su
    miniatura no necesita ninguna llamada extra: img.youtube.com/vi/<id>/...
    es una URL pública y estable a partir del ID, sin API key — la key solo
    hace falta para *encontrar* el video vía búsqueda.

    Best-effort a propósito: si YouTube no tiene resultados o la búsqueda
    falla, el match se devuelve como llegó (cae al texto plano en el
    cliente) — un fallback opcional no debe poder romper una identificación
    que sí funcionó."""
    if match.cover_url or not youtube_api_key:
        return match

    try:
        videos = search_youtube(f"{match.artist} {match.title}", youtube_api_key, max_results=1)
    except (YouTubeNotConfigured, requests.RequestException) as exc:
        logger.warning("Fallback de portada a YouTube falló (se ignora, no es crítico): %s", exc)
        return match

    if not videos:
        return match

    video_id = videos[0].url.rsplit("v=", 1)[-1]
    match.cover_url = f"https://img.youtube.com/vi/{video_id}/mqdefault.jpg"
    match.track_url = videos[0].url
    return match


@router.post("/identify", response_model=IdentifySongResponse)
async def identify(audio: UploadFile) -> IdentifySongResponse:
    """Identifica una canción a partir de un fragmento de audio grabado por
    el cliente (PC o celular) — directo, sin pasar por tool calling, mismo
    criterio que /voice/transcribe y /vision/analyze."""
    audio_bytes = await audio.read()
    settings = get_settings()
    try:
        match = identify_song(audio_bytes, api_token=settings.audd_api_token)
    except AuddNotConfigured as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except AuddError as exc:
        # 502 y no 500: el fallo es del servicio externo, no de ATLAS. Un 500
        # sin manejar además se rompe de forma confusa en el navegador —
        # FastAPI no le agrega cabeceras CORS, así que el cliente reporta un
        # error de CORS en vez del motivo real (visto en vivo).
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except requests.RequestException as exc:
        raise HTTPException(
            status_code=502, detail=f"No se pudo contactar a AudD: {exc}"
        ) from exc

    if match is None:
        return IdentifySongResponse(found=False)

    match = _fill_cover_from_youtube(match, settings.youtube_api_key)

    return IdentifySongResponse(
        found=True,
        artist=match.artist,
        title=match.title,
        album=match.album,
        song_link=match.song_link,
        cover_url=match.cover_url,
        track_url=match.track_url,
    )
