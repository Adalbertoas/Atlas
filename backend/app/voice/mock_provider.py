"""Providers de voz deterministas, sin dependencias pesadas ni descargas.

Mismo criterio que MockProvider de IA (app/ai/mock_provider.py): permiten
correr tests y desarrollar sin instalar faster-whisper/pyttsx3.
"""
from __future__ import annotations

import struct

from app.voice.base import SpeechToTextProvider, TextToSpeechProvider


class MockSTTProvider(SpeechToTextProvider):
    def transcribe(self, audio_bytes: bytes, language: str | None = None) -> str:
        return "texto simulado (configura STT_PROVIDER=whisper para transcripción real)"


def _silent_wav(seconds: float = 0.2, sample_rate: int = 16000) -> bytes:
    """Genera un WAV PCM16 mono válido, en silencio, sin depender de ninguna
    librería de audio — suficiente para que los tests validen el formato."""
    num_samples = int(seconds * sample_rate)
    data = b"\x00\x00" * num_samples
    byte_rate = sample_rate * 2
    header = struct.pack(
        "<4sI4s4sIHHIIHH4sI",
        b"RIFF",
        36 + len(data),
        b"WAVE",
        b"fmt ",
        16,
        1,  # PCM
        1,  # mono
        sample_rate,
        byte_rate,
        2,
        16,
        b"data",
        len(data),
    )
    return header + data


class MockTTSProvider(TextToSpeechProvider):
    def synthesize(self, text: str) -> bytes:
        return _silent_wav()
