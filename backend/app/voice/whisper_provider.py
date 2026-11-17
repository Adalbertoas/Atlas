"""SpeechToTextProvider usando Whisper local (faster-whisper).

Gratis, sin internet. El modelo se descarga solo la primera vez que se usa
(cacheado por faster-whisper en el equipo).
"""
from __future__ import annotations

from faster_whisper import WhisperModel

from app.voice.audio import decode_audio
from app.voice.base import SpeechToTextProvider


class WhisperLocalProvider(SpeechToTextProvider):
    def __init__(self, model_size: str = "base") -> None:
        # compute_type="int8": corre bien en CPU sin necesitar GPU.
        self._model = WhisperModel(model_size, device="cpu", compute_type="int8")

    def transcribe(
        self,
        audio_bytes: bytes,
        language: str | None = None,
        *,
        fast: bool = False,
        prompt: str | None = None,
    ) -> str:
        pcm = decode_audio(audio_bytes)
        if pcm.size == 0:
            return ""
        segments, _info = self._model.transcribe(
            pcm,
            language=language,
            # Las parciales usan búsqueda voraz: bastante más rápida y casi
            # igual de precisa en frases cortas.
            beam_size=1 if fast else 5,
            initial_prompt=prompt or None,
            # Cada clip es independiente: arrastrar texto previo solo
            # propaga alucinaciones entre segmentos.
            condition_on_previous_text=False,
            without_timestamps=True,
            # Silero VAD (incluido en faster-whisper) recorta lo que no es voz.
            # Un clip de solo ruido (música, golpes, ventilador) sale vacío en
            # ~10 ms en vez de ~650 ms, y Whisper no inventa texto sobre él.
            vad_filter=True,
            vad_parameters={"threshold": 0.4, "min_silence_duration_ms": 500, "speech_pad_ms": 300},
        )
        return " ".join(segment.text.strip() for segment in segments).strip()
