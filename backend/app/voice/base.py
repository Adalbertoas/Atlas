"""Interfaces abstractas de voz de ATLAS (sección 7 del prompt maestro).

Pipeline: Micrófono -> SpeechToTextProvider -> ATLAS Core -> AI ->
TextToSpeechProvider -> Audio.

Igual que AIProvider (app/ai/base.py): ningún otro módulo debe importar
`faster_whisper` o `pyttsx3` directamente, todo pasa por estas interfaces.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from enum import Enum


class SpeechToTextProvider(ABC):
    @abstractmethod
    def transcribe(self, audio_bytes: bytes, language: str | None = None) -> str:
        """Convierte audio (WAV) a texto."""
        raise NotImplementedError


class TextToSpeechProvider(ABC):
    @abstractmethod
    def synthesize(self, text: str) -> bytes:
        """Convierte texto a audio (WAV)."""
        raise NotImplementedError


class VoiceMode(str, Enum):
    PUSH_TO_TALK = "PUSH_TO_TALK"
    WAKE_WORD = "WAKE_WORD"


class VoiceActivationProvider(ABC):
    """Decide cuándo se debe capturar/enviar audio para transcribir.

    En Fase 3 solo existe PushToTalkProvider (el cliente decide, sin lógica
    de servidor). WAKE_WORD ("Hey ATLAS") requiere escucha continua +
    detección de palabra clave y queda para una fase posterior — ver
    docs/architecture.md.
    """

    mode: VoiceMode

    @abstractmethod
    def is_active(self) -> bool:
        """Si el modo de activación actual permite iniciar una captura."""
        raise NotImplementedError
