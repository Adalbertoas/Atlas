"""Tests del proveedor de voz neuronal (Edge TTS, Fase 18).

Mockean la red: no le pegan al servicio de Microsoft ni dependen de tener
conexión, igual criterio que el resto de las integraciones externas.
"""
from __future__ import annotations

import io
from unittest.mock import patch

import numpy as np
import pytest
import soundfile as sf

from app.voice.edge_provider import DEFAULT_VOICE, EdgeTTSProvider, _mp3_to_wav


def _fake_mp3(seconds: float = 0.2, sample_rate: int = 24000) -> bytes:
    """MP3 real (generado con soundfile) para ejercitar la conversión."""
    tone = np.sin(2 * np.pi * 440 * np.linspace(0, seconds, int(sample_rate * seconds)))
    buffer = io.BytesIO()
    sf.write(buffer, tone, sample_rate, format="MP3")
    return buffer.getvalue()


def test_default_voice_is_the_one_chosen():
    assert DEFAULT_VOICE == "es-MX-JorgeNeural"


def test_empty_text_returns_no_audio():
    """Sin esto se le pediría a Edge sintetizar la nada y devolvería error."""
    assert EdgeTTSProvider().synthesize("") == b""
    assert EdgeTTSProvider().synthesize("   ") == b""


def test_output_is_wav_not_mp3():
    """Edge devuelve MP3, pero el cliente de escritorio reproduce con
    soundfile esperando WAV — la conversión no es opcional."""
    provider = EdgeTTSProvider()
    with patch.object(EdgeTTSProvider, "_synthesize_mp3", return_value=_fake_mp3()):
        audio = provider.synthesize("hola")

    assert audio[:4] == b"RIFF"  # cabecera WAV
    assert audio[8:12] == b"WAVE"


def test_converted_audio_is_readable():
    with patch.object(EdgeTTSProvider, "_synthesize_mp3", return_value=_fake_mp3()):
        audio = EdgeTTSProvider().synthesize("hola")

    data, rate = sf.read(io.BytesIO(audio))
    assert len(data) > 0
    assert rate > 0


def test_mp3_to_wav_preserves_sample_rate():
    wav = _mp3_to_wav(_fake_mp3(sample_rate=24000))
    _, rate = sf.read(io.BytesIO(wav))
    assert rate == 24000


def test_voice_and_prosody_reach_the_api():
    """La voz configurable es el punto de toda la fase: si no se propaga,
    cambiar EDGE_TTS_VOICE en .env no haría nada."""
    captured = {}

    class FakeCommunicate:
        def __init__(self, text, voice, rate=None, pitch=None):
            captured.update(text=text, voice=voice, rate=rate, pitch=pitch)

        async def stream(self):
            yield {"type": "audio", "data": _fake_mp3()}

    fake_module = type("edge_tts", (), {"Communicate": FakeCommunicate})
    with patch.dict("sys.modules", {"edge_tts": fake_module}):
        EdgeTTSProvider(voice="es-CO-GonzaloNeural", rate="+10%", pitch="-5Hz").synthesize("probando")

    assert captured["voice"] == "es-CO-GonzaloNeural"
    assert captured["rate"] == "+10%"
    assert captured["pitch"] == "-5Hz"
    assert captured["text"] == "probando"


def test_blank_voice_falls_back_to_default():
    """Un EDGE_TTS_VOICE vacío en .env no debe dejar a ATLAS mudo."""
    assert EdgeTTSProvider(voice="")._voice == DEFAULT_VOICE


def test_factory_selects_edge_when_configured(monkeypatch):
    from app.api.deps import get_tts_provider
    from app.config import get_settings

    monkeypatch.setenv("TTS_PROVIDER", "edge")
    monkeypatch.setenv("EDGE_TTS_VOICE", "es-AR-ElenaNeural")
    get_settings.cache_clear()
    get_tts_provider.cache_clear()

    provider = get_tts_provider()

    get_settings.cache_clear()
    get_tts_provider.cache_clear()
    assert isinstance(provider, EdgeTTSProvider)
    assert provider._voice == "es-AR-ElenaNeural"


@pytest.mark.parametrize("provider_name", ["sapi", "mock", "cualquier-otra-cosa"])
def test_factory_does_not_use_edge_for_other_providers(provider_name, monkeypatch):
    """SAPI sigue disponible: Edge necesita internet y usa una vía no
    oficial, así que la alternativa offline no se puede perder."""
    from app.api.deps import get_tts_provider
    from app.config import get_settings

    monkeypatch.setenv("TTS_PROVIDER", provider_name)
    get_settings.cache_clear()
    get_tts_provider.cache_clear()
    try:
        provider = get_tts_provider()
    except Exception:
        return  # sapi puede no cargar en CI sin pyttsx3; lo que importa es que no es Edge
    finally:
        get_settings.cache_clear()
        get_tts_provider.cache_clear()

    assert not isinstance(provider, EdgeTTSProvider)
