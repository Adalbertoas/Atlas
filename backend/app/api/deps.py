"""Dependencias compartidas de la API (inyección de sesión DB, orchestrator, etc.)."""
from __future__ import annotations

from collections.abc import Generator
from functools import lru_cache

from sqlalchemy.orm import Session

from app.ai.anthropic_provider import AnthropicProvider
from app.ai.base import AIProvider
from app.ai.mock_provider import MockProvider
from app.config import get_settings
from app.core.database import get_db
from app.core.orchestrator import Orchestrator
from app.events.bus import event_bus
from app.security.permissions import permission_manager
from app.tools.registry import tool_registry
from app.voice.base import SpeechToTextProvider, TextToSpeechProvider
from app.voice.mock_provider import MockSTTProvider, MockTTSProvider


def get_db_session() -> Generator[Session, None, None]:
    yield from get_db()


@lru_cache
def _build_ai_provider() -> AIProvider:
    settings = get_settings()
    if settings.ai_provider == "anthropic":
        return AnthropicProvider(api_key=settings.anthropic_api_key, model=settings.anthropic_model)
    return MockProvider()


@lru_cache
def get_orchestrator() -> Orchestrator:
    return Orchestrator(
        ai_provider=_build_ai_provider(),
        registry=tool_registry,
        permissions=permission_manager,
        events=event_bus,
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
    if settings.tts_provider == "edge":
        from app.voice.edge_provider import EdgeTTSProvider  # import perezoso: solo si se usa

        return EdgeTTSProvider(
            voice=settings.edge_tts_voice,
            rate=settings.edge_tts_rate,
            pitch=settings.edge_tts_pitch,
        )
    if settings.tts_provider == "sapi":
        from app.voice.sapi_provider import WindowsSapiProvider  # import perezoso: pyttsx3 solo en Windows

        return WindowsSapiProvider()
    return MockTTSProvider()
