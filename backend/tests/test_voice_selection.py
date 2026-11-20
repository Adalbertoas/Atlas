"""Elegir la voz de ATLAS desde los clientes (GET /voice/voices, PUT /voice)."""
from __future__ import annotations

import pytest

from app.api.deps import get_tts_provider
from app.main import app
from app.voice import voices
from app.voice.base import TextToSpeechProvider


class _FakeKokoro(TextToSpeechProvider):
    supports_voices = True

    def __init__(self) -> None:
        self._voice, self._speed = "em_alex", 1.0
        self.spoken: list[tuple[str, str | None, float | None]] = []

    @property
    def voice(self) -> str:
        return self._voice

    @property
    def speed(self) -> float:
        return self._speed

    def set_voice(self, voice: str, speed: float | None = None) -> None:
        self._voice = voice
        if speed is not None:
            self._speed = speed

    def synthesize(self, text: str) -> bytes:
        return self.synthesize_as(text)

    def synthesize_as(self, text: str, voice: str | None = None, speed: float | None = None) -> bytes:
        self.spoken.append((text, voice, speed))
        return b"RIFF-fake"


@pytest.fixture()
def fake_tts(tmp_path, monkeypatch):
    tts = _FakeKokoro()
    env = tmp_path / ".env"
    env.write_text("TTS_PROVIDER=kokoro\nKOKORO_VOICE=em_alex\n", encoding="utf-8")
    from app.core import keys

    # Nunca escribir el backend/.env real desde un test.
    monkeypatch.setattr(voices, "write_env_value", lambda name, value: keys.write_env_value(name, value, path=env))
    app.dependency_overrides[get_tts_provider] = lambda: tts
    yield tts, env
    app.dependency_overrides.pop(get_tts_provider, None)


def test_lists_spanish_voices(client, auth_headers, fake_tts):
    body = client.get("/api/v1/voice/voices", headers=auth_headers).json()
    assert body["available"] is True and body["current"] == "em_alex"
    assert {v["id"] for v in body["voices"]} == {"em_alex", "em_santa", "ef_dora"}


def test_choosing_a_voice_applies_and_persists(client, auth_headers, fake_tts):
    tts, env = fake_tts
    response = client.put("/api/v1/voice/voice", json={"voice": "ef_dora", "speed": 1.1}, headers=auth_headers)
    assert response.status_code == 200
    assert response.json()["current"] == "ef_dora" and tts.voice == "ef_dora" and tts.speed == 1.1
    saved = env.read_text(encoding="utf-8")
    assert "KOKORO_VOICE=ef_dora" in saved and "KOKORO_SPEED=1.1" in saved
    assert "TTS_PROVIDER=kokoro" in saved  # el resto del .env queda igual


@pytest.mark.parametrize("body", [{"voice": "af_heart"}, {"voice": "em_alex", "speed": 3}])
def test_rejects_unknown_voice_or_speed(client, auth_headers, fake_tts, body):
    assert client.put("/api/v1/voice/voice", json=body, headers=auth_headers).status_code == 400


def test_preview_uses_the_requested_voice_without_changing_default(client, auth_headers, fake_tts):
    tts, _ = fake_tts
    response = client.post("/api/v1/voice/speak", json={"text": "hola", "voice": "em_santa"}, headers=auth_headers)
    assert response.status_code == 200
    assert tts.spoken[-1] == ("hola", "em_santa", None) and tts.voice == "em_alex"


def test_providers_without_voices_say_so(client, auth_headers):
    body = client.get("/api/v1/voice/voices", headers=auth_headers).json()  # TTS mock en los tests
    assert body["available"] is False and body["voices"] == []
    response = client.put("/api/v1/voice/voice", json={"voice": "ef_dora"}, headers=auth_headers)
    assert response.status_code == 400 and "kokoro" in response.json()["detail"]
