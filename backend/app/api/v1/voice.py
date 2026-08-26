from __future__ import annotations

from fastapi import APIRouter, Depends, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel

from app.api.deps import get_stt_provider, get_tts_provider
from app.voice.base import SpeechToTextProvider, TextToSpeechProvider

router = APIRouter(prefix="/voice", tags=["voice"])


class TranscribeResponse(BaseModel):
    text: str


class SpeakRequest(BaseModel):
    text: str


@router.post("/transcribe", response_model=TranscribeResponse)
async def transcribe(
    audio: UploadFile,
    language: str | None = "es",
    stt: SpeechToTextProvider = Depends(get_stt_provider),
) -> TranscribeResponse:
    # Por defecto se fuerza español: en clips cortos/ambiguos (típico del
    # modo wake word, que transcribe ventanas de pocos segundos) la
    # detección automática de idioma de Whisper resultó nada confiable en
    # pruebas reales — llegó a transcribir "Atlas" en alfabeto cirílico por
    # detectar mal el idioma. Se puede pasar language=None explícitamente
    # para volver a la detección automática si hace falta.
    audio_bytes = await audio.read()
    text = stt.transcribe(audio_bytes, language=language)
    return TranscribeResponse(text=text)


@router.post("/speak")
def speak(body: SpeakRequest, tts: TextToSpeechProvider = Depends(get_tts_provider)) -> Response:
    audio_bytes = tts.synthesize(body.text)
    return Response(content=audio_bytes, media_type="audio/wav")
