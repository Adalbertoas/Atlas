from __future__ import annotations

import asyncio
import logging

from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import Response
from pydantic import BaseModel

from app.api.deps import get_speaker_verifier, get_stt_provider, get_tts_provider
from app.core.keys import KeySettingError
from app.voice import voices
from app.voice.audio import decode_audio
from app.voice.base import SpeechToTextProvider, TextToSpeechProvider
from app.voice.speaker import SpeakerVerifier

router = APIRouter(prefix="/voice", tags=["voice"])
logger = logging.getLogger(__name__)

MAX_ENROLL_SAMPLES = 6


class TranscribeResponse(BaseModel):
    text: str
    # Solo con speaker=true: parecido con la voz registrada (-1..1), o null si
    # no hay voz registrada o la frase es demasiado corta para juzgarla.
    speaker_score: float | None = None


class SpeakRequest(BaseModel):
    text: str
    # Otra voz solo para este audio (escuchar una voz antes de elegirla).
    voice: str | None = None
    speed: float | None = None


class ChooseVoiceRequest(BaseModel):
    voice: str
    speed: float | None = None


class SpeakerStatus(BaseModel):
    available: bool  # el modelo de huella de voz está descargado
    enrolled: bool
    samples: int = 0
    consistency: float | None = None
    created_at: str | None = None


def _speaker_score(verifier: SpeakerVerifier, audio_bytes: bytes) -> float | None:
    if not verifier.available:
        return None
    try:
        return verifier.score(decode_audio(audio_bytes))
    except Exception:  # noqa: BLE001 — un audio raro no debe tirar la transcripción
        return None


@router.post("/transcribe", response_model=TranscribeResponse)
async def transcribe(
    audio: UploadFile,
    language: str | None = "es",
    fast: bool = False,
    prompt: str | None = Query(default=None, max_length=200),
    speaker: bool = False,
    speaker_min: float | None = Query(default=None, ge=-1, le=1),
    stt: SpeechToTextProvider = Depends(get_stt_provider),
    verifier: SpeakerVerifier = Depends(get_speaker_verifier),
) -> TranscribeResponse:
    # Por defecto se fuerza español: en clips cortos/ambiguos (típico del
    # modo wake word, que transcribe ventanas de pocos segundos) la
    # detección automática de idioma de Whisper resultó nada confiable en
    # pruebas reales — llegó a transcribir "Atlas" en alfabeto cirílico por
    # detectar mal el idioma. Se puede pasar language=None explícitamente
    # para volver a la detección automática si hace falta.
    # fast=true: transcripción parcial (mientras el usuario sigue hablando).
    # prompt: sesga el vocabulario, p. ej. hacia la palabra de activación.
    # speaker=true: además, compara la voz con la registrada ("solo mi voz").
    # speaker_min: si la voz queda por debajo, no se transcribe (text="").
    audio_bytes = await audio.read()
    # Whisper tarda cientos de ms y es síncrono: en un hilo aparte para no
    # bloquear el resto del backend (chat, eventos) mientras transcribe.
    transcribe_audio = lambda: run_in_threadpool(stt.transcribe, audio_bytes, language=language, fast=fast, prompt=prompt)  # noqa: E731
    if not speaker:
        return TranscribeResponse(text=await transcribe_audio())
    if speaker_min is not None:
        # Primero la huella (~65 ms): la voz de otra persona (o la tele) no
        # llega a Whisper (~650 ms de CPU por frase).
        score = await run_in_threadpool(_speaker_score, verifier, audio_bytes)
        # Solo la puntuación (nunca el texto): sirve para ajustar la exigencia.
        logger.info(
            "Solo mi voz: parecido %s (minimo %.2f) -> %s",
            "?" if score is None else f"{score:.2f}",
            speaker_min,
            "otra voz, no se transcribe" if score is not None and score < speaker_min else "se transcribe",
        )
        if score is not None and score < speaker_min:
            return TranscribeResponse(text="", speaker_score=score)
        return TranscribeResponse(text=await transcribe_audio(), speaker_score=score)
    # Sin umbral: ambas cosas en paralelo.
    text, score = await asyncio.gather(transcribe_audio(), run_in_threadpool(_speaker_score, verifier, audio_bytes))
    return TranscribeResponse(text=text, speaker_score=score)


@router.post("/speak")
def speak(body: SpeakRequest, tts: TextToSpeechProvider = Depends(get_tts_provider)) -> Response:
    if body.voice is None and body.speed is None:
        audio_bytes = tts.synthesize(body.text)
    else:
        try:
            voices.validate(body.voice, body.speed)
        except KeySettingError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        audio_bytes = tts.synthesize_as(body.text, voice=body.voice, speed=body.speed)
    return Response(content=audio_bytes, media_type="audio/wav")


# ---------- Elegir la voz de ATLAS (compartida por la PC y la tablet) ----------


@router.get("/voices")
def list_voices(tts: TextToSpeechProvider = Depends(get_tts_provider)) -> dict:
    return voices.status(tts)


@router.put("/voice")
def choose_voice(body: ChooseVoiceRequest, tts: TextToSpeechProvider = Depends(get_tts_provider)) -> dict:
    try:
        return voices.choose(tts, body.voice, body.speed)
    except KeySettingError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


# ---------- Huella de voz ("solo responder a mi voz") ----------
# Se guarda un vector numérico (no audio) en backend/speaker_profile.json.


def _status(verifier: SpeakerVerifier) -> SpeakerStatus:
    profile = verifier.profile()
    if profile is None:
        return SpeakerStatus(available=verifier.available, enrolled=False)
    return SpeakerStatus(
        available=verifier.available,
        enrolled=True,
        samples=profile.get("samples", 0),
        consistency=profile.get("consistency"),
        created_at=profile.get("created_at"),
    )


@router.get("/speaker", response_model=SpeakerStatus)
def speaker_status(verifier: SpeakerVerifier = Depends(get_speaker_verifier)) -> SpeakerStatus:
    return _status(verifier)


@router.post("/speaker/enroll", response_model=SpeakerStatus)
async def speaker_enroll(
    samples: list[UploadFile],
    verifier: SpeakerVerifier = Depends(get_speaker_verifier),
) -> SpeakerStatus:
    if not verifier.available:
        raise HTTPException(
            status_code=503,
            detail="Falta el modelo de huella de voz. Ejecuta: python scripts/download_speaker_model.py",
        )
    if not 2 <= len(samples) <= MAX_ENROLL_SAMPLES:
        raise HTTPException(status_code=422, detail=f"Envia entre 2 y {MAX_ENROLL_SAMPLES} frases.")
    audios = [decode_audio(await sample.read()) for sample in samples]
    try:
        await run_in_threadpool(verifier.enroll, audios)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return _status(verifier)


@router.delete("/speaker", response_model=SpeakerStatus)
def speaker_delete(verifier: SpeakerVerifier = Depends(get_speaker_verifier)) -> SpeakerStatus:
    verifier.delete()
    return _status(verifier)
