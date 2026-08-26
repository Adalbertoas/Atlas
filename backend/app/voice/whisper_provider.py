"""SpeechToTextProvider usando Whisper local (faster-whisper).

Gratis, sin internet. El modelo se descarga solo la primera vez que se usa
(cacheado por faster-whisper en el equipo).
"""
from __future__ import annotations

import io

from faster_whisper import WhisperModel

from app.voice.base import SpeechToTextProvider


class WhisperLocalProvider(SpeechToTextProvider):
    def __init__(self, model_size: str = "base") -> None:
        # compute_type="int8": corre bien en CPU sin necesitar GPU.
        self._model = WhisperModel(model_size, device="cpu", compute_type="int8")

    def transcribe(self, audio_bytes: bytes, language: str | None = None) -> str:
        segments, _info = self._model.transcribe(
            io.BytesIO(audio_bytes), language=language, beam_size=5
        )
        return " ".join(segment.text.strip() for segment in segments).strip()
