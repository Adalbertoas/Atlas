"""Voces de ATLAS que se pueden elegir desde los clientes (Kokoro, en español).

La elegida se guarda en backend/.env (KOKORO_VOICE / KOKORO_SPEED), así la PC
y la tablet hablan con la misma voz. Cada voz pesa ~500 KB y Kokoro la baja de
Hugging Face la primera vez que se usa.
"""
from __future__ import annotations

from app.config import get_settings
from app.core.keys import KeySettingError, write_env_value
from app.voice.base import TextToSpeechProvider

SPANISH_VOICES = [
    {"id": "em_alex", "name": "Alex", "gender": "hombre", "description": "Masculina, clara y neutra."},
    {"id": "em_santa", "name": "Santa", "gender": "hombre", "description": "Masculina, más grave y pausada."},
    {"id": "ef_dora", "name": "Dora", "gender": "mujer", "description": "Femenina, cálida."},
]
VOICE_IDS = {v["id"] for v in SPANISH_VOICES}
MIN_SPEED, MAX_SPEED = 0.7, 1.4


def status(tts: TextToSpeechProvider) -> dict:
    return {
        "available": tts.supports_voices,
        "provider": get_settings().tts_provider,
        "current": tts.voice,
        "speed": tts.speed,
        "min_speed": MIN_SPEED,
        "max_speed": MAX_SPEED,
        "voices": SPANISH_VOICES if tts.supports_voices else [],
    }


def validate(voice: str | None, speed: float | None) -> None:
    if voice is not None and voice not in VOICE_IDS:
        raise KeySettingError(f"Voz desconocida: {voice}.")
    if speed is not None and not MIN_SPEED <= speed <= MAX_SPEED:
        raise KeySettingError(f"La velocidad debe estar entre {MIN_SPEED} y {MAX_SPEED}.")


def choose(tts: TextToSpeechProvider, voice: str, speed: float | None = None) -> dict:
    """Cambia la voz por defecto en caliente y la deja guardada en el .env."""
    if not tts.supports_voices:
        raise KeySettingError("La voz solo se puede elegir con TTS_PROVIDER=kokoro en el backend.")
    validate(voice, speed)
    speed = round(speed, 2) if speed is not None else None
    tts.set_voice(voice, speed)
    settings = get_settings()
    write_env_value("KOKORO_VOICE", voice)
    settings.kokoro_voice = voice
    if speed is not None:
        write_env_value("KOKORO_SPEED", str(speed))
        settings.kokoro_speed = speed
    return status(tts)
