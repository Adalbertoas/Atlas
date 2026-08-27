from __future__ import annotations

import requests
from fastapi import APIRouter, HTTPException, UploadFile
from pydantic import BaseModel

from app.config import get_settings
from app.integrations.audd import AuddError, AuddNotConfigured, identify_song

router = APIRouter(prefix="/music", tags=["music"])


class IdentifySongResponse(BaseModel):
    found: bool
    artist: str | None = None
    title: str | None = None
    album: str | None = None
    song_link: str | None = None


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
    return IdentifySongResponse(
        found=True, artist=match.artist, title=match.title, album=match.album, song_link=match.song_link
    )
