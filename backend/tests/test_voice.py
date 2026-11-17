from __future__ import annotations

from dataclasses import dataclass

from app.voice.mock_provider import MockSTTProvider, MockTTSProvider
from app.voice.push_to_talk import PushToTalkProvider
from app.voice.sapi_provider import _pick_voice_id


@dataclass
class _FakeVoice:
    id: str
    name: str
    languages: list = None


class _FakeEngine:
    def __init__(self, voices: list[_FakeVoice]) -> None:
        self._voices = voices

    def getProperty(self, name: str):  # noqa: N802 — nombre impuesto por pyttsx3
        assert name == "voices"
        return self._voices


def test_mock_stt_returns_placeholder_text():
    provider = MockSTTProvider()
    text = provider.transcribe(b"fake-audio-bytes")
    assert isinstance(text, str)
    assert text


def test_mock_tts_returns_valid_wav_header():
    provider = MockTTSProvider()
    audio = provider.synthesize("Hola, soy ATLAS")
    assert audio[:4] == b"RIFF"
    assert audio[8:12] == b"WAVE"


def test_push_to_talk_is_always_active():
    provider = PushToTalkProvider()
    assert provider.is_active() is True


def test_transcribe_endpoint(client, auth_headers):
    response = client.post(
        "/api/v1/voice/transcribe",
        files={"audio": ("audio.wav", b"fake-audio-bytes", "audio/wav")},
        headers=auth_headers,
    )
    assert response.status_code == 200
    assert response.json()["text"]


def test_speak_endpoint_returns_wav_audio(client, auth_headers):
    response = client.post("/api/v1/voice/speak", json={"text": "Hola, soy ATLAS"}, headers=auth_headers)
    assert response.status_code == 200
    assert response.headers["content-type"] == "audio/wav"
    assert response.content[:4] == b"RIFF"


def test_pick_voice_id_prefers_spanish_voice():
    engine = _FakeEngine(
        [
            _FakeVoice(id="...EN-US_DAVID...", name="Microsoft David - English (United States)"),
            _FakeVoice(id="...ES-ES_HELENA...", name="Microsoft Helena - Spanish (Spain)"),
        ]
    )
    assert _pick_voice_id(engine) == "...ES-ES_HELENA..."


def test_pick_voice_id_returns_none_when_no_spanish_voice_installed():
    # Este es exactamente el caso real detectado: Windows solo tenía David y
    # Zira instaladas (en-US) — sin voz en español, ATLAS debe caer en la
    # voz por defecto en vez de fallar.
    engine = _FakeEngine(
        [
            _FakeVoice(id="...EN-US_DAVID...", name="Microsoft David Desktop - English (United States)"),
            _FakeVoice(id="...EN-US_ZIRA...", name="Microsoft Zira Desktop - English (United States)"),
        ]
    )
    assert _pick_voice_id(engine) is None


class _RecordingSTT(MockSTTProvider):
    def __init__(self) -> None:
        self.calls: list[dict] = []

    def transcribe(self, audio_bytes, language=None, *, fast=False, prompt=None):
        self.calls.append({"language": language, "fast": fast, "prompt": prompt})
        return "hola"


def test_transcribe_endpoint_forwards_fast_and_prompt(client, auth_headers):
    from app.api.deps import get_stt_provider
    from app.main import app

    stt = _RecordingSTT()
    app.dependency_overrides[get_stt_provider] = lambda: stt
    response = client.post(
        "/api/v1/voice/transcribe",
        params={"fast": "true", "prompt": "Atlas."},
        files={"audio": ("audio.wav", b"fake-audio-bytes", "audio/wav")},
        headers=auth_headers,
    )
    assert response.status_code == 200
    assert response.json()["text"] == "hola"
    assert stt.calls == [{"language": "es", "fast": True, "prompt": "Atlas."}]


def test_transcribe_endpoint_defaults_to_accurate_mode(client, auth_headers):
    from app.api.deps import get_stt_provider
    from app.main import app

    stt = _RecordingSTT()
    app.dependency_overrides[get_stt_provider] = lambda: stt
    client.post(
        "/api/v1/voice/transcribe",
        files={"audio": ("audio.wav", b"fake-audio-bytes", "audio/wav")},
        headers=auth_headers,
    )
    assert stt.calls == [{"language": "es", "fast": False, "prompt": None}]


def test_pcm16_wav_is_decoded_without_ffmpeg():
    import io
    import wave

    import numpy as np
    import pytest

    pytest.importorskip("faster_whisper")
    from app.voice.audio import pcm16_wav_to_float

    samples = np.array([0, 16384, -32768, 32767], dtype="<i2")
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(16000)
        wav.writeframes(samples.tobytes())
    decoded = pcm16_wav_to_float(buffer.getvalue())
    assert decoded is not None
    assert decoded.dtype == np.float32
    assert np.allclose(decoded, [0.0, 0.5, -1.0, 32767 / 32768])


def test_non_16k_or_non_wav_audio_falls_back_to_generic_decoder():
    import io
    import wave

    import pytest

    pytest.importorskip("faster_whisper")
    from app.voice.audio import pcm16_wav_to_float

    assert pcm16_wav_to_float(b"\x1aE\xdf\xa3webm-bytes") is None
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(48000)
        wav.writeframes(b"\x00\x00" * 10)
    assert pcm16_wav_to_float(buffer.getvalue()) is None
