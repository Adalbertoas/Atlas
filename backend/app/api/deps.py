"""Dependencias compartidas de la API (inyección de sesión DB, orchestrator, etc.)."""
from __future__ import annotations

from collections.abc import Generator
from functools import lru_cache
from pathlib import Path

from sqlalchemy.orm import Session

from app.ai.base import AIProvider
from app.ai.factory import build_ai_provider
from app.config import get_settings
from app.core.database import get_db
from app.core.orchestrator import Orchestrator
from app.events.bus import event_bus
from app.security.permissions import permission_manager
from app.tools.registry import tool_registry
from app.voice.base import SpeechToTextProvider, TextToSpeechProvider
from app.voice.mock_provider import MockSTTProvider, MockTTSProvider
from app.voice.speaker import SPEAKER_MODEL_FILE, SpeakerVerifier


def get_db_session() -> Generator[Session, None, None]:
    yield from get_db()


@lru_cache
def _build_ai_provider() -> AIProvider:
    return build_ai_provider()


@lru_cache
def get_orchestrator() -> Orchestrator:
    from app.vision.provider_factory import get_vision_provider

    return Orchestrator(
        ai_provider=_build_ai_provider(),
        registry=tool_registry,
        permissions=permission_manager,
        events=event_bus,
        vision=get_vision_provider(),
    )


@lru_cache
def get_stt_provider() -> SpeechToTextProvider:
    settings = get_settings()
    if settings.stt_provider == "whisper":
        from app.voice.whisper_provider import WhisperLocalProvider  # import perezoso: faster-whisper es pesado

        return WhisperLocalProvider(model_size=settings.whisper_model_size)
    return MockSTTProvider()


@lru_cache
def get_tts_provider() -> TextToSpeechProvider:
    settings = get_settings()
    if settings.tts_provider == "kokoro":
        from app.voice.kokoro_provider import KokoroProvider  # import perezoso: el modelo se carga al hablar

        return KokoroProvider(
            voice=settings.kokoro_voice,
            speed=settings.kokoro_speed,
            cache_dir=settings.kokoro_cache_dir,
        )
    if settings.tts_provider == "sapi":
        from app.voice.sapi_provider import WindowsSapiProvider  # import perezoso: pyttsx3 solo en Windows

        return WindowsSapiProvider()
    return MockTTSProvider()


@lru_cache
def get_speaker_verifier() -> SpeakerVerifier:
    settings = get_settings()
    backend_dir = Path(__file__).resolve().parents[2]
    model = Path(settings.speaker_model_path) if settings.speaker_model_path else backend_dir.parent / ".cache" / "speaker" / SPEAKER_MODEL_FILE
    profile = Path(settings.speaker_profile_path) if settings.speaker_profile_path else backend_dir / "speaker_profile.json"
    return SpeakerVerifier(model_path=model, profile_path=profile)
