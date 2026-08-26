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
