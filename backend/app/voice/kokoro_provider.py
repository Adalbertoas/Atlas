"""Proveedor local de voz Kokoro inspirado en el enfoque local-first de OpenJarvis.

Kokoro genera voz de alta calidad en el equipo: no envía el texto a un
proveedor externo. La primera síntesis descarga/cachea los pesos del modelo.
"""
from __future__ import annotations

import io
import threading
from typing import Any

from app.voice.base import TextToSpeechProvider


class KokoroProvider(TextToSpeechProvider):
    """Text-to-speech local con una voz Kokoro configurable."""

    def __init__(self, voice: str = "ef_dora", speed: float = 1.0) -> None:
        if not 0.5 <= speed <= 2.0:
            raise ValueError("KOKORO_SPEED debe estar entre 0.5 y 2.0.")
        self._voice = voice or "ef_dora"
        self._speed = speed
        self._pipeline: Any | None = None
        self._lock = threading.RLock()

    def _get_pipeline(self) -> Any:
        if self._pipeline is not None:
            return self._pipeline
        try:
            from kokoro import KPipeline
        except ImportError as exc:
            raise RuntimeError(
                "Kokoro no está instalado. Ejecutá: pip install 'kokoro>=0.9.4'"
            ) from exc

        # Las voces Kokoro comienzan con el código del idioma: e=español,
        # a=inglés americano, b=inglés británico, etc.
        language = self._voice[0].lower()
        self._pipeline = KPipeline(lang_code=language)
        return self._pipeline

    def synthesize(self, text: str) -> bytes:
        if not text.strip():
            return b""
        try:
            import numpy as np
            import soundfile as sf
        except ImportError as exc:
            raise RuntimeError("Kokoro requiere numpy y soundfile.") from exc

        with self._lock:
            pipeline = self._get_pipeline()
            samples = [audio for _, _, audio in pipeline(text, voice=self._voice, speed=self._speed)]

        if not samples:
            return b""
        output = io.BytesIO()
        sf.write(output, np.concatenate(samples), 24000, format="WAV")
        return output.getvalue()