from __future__ import annotations

import io
import wave
from pathlib import Path

import numpy as np
import pytest

from app.voice.speaker import SPEAKER_MODEL_FILE, SpeakerVerifier, cosine, kaldi_fbank

MODEL = Path(__file__).resolve().parents[2] / ".cache" / "speaker" / SPEAKER_MODEL_FILE


def _tone(seconds: float, freq: float = 220.0, seed: int = 0) -> np.ndarray:
    t = np.arange(int(seconds * 16000)) / 16000
    rng = np.random.default_rng(seed)
    return (0.3 * np.sin(2 * np.pi * freq * t) + rng.normal(0, 0.01, t.size)).astype(np.float32)


def _wav(audio: np.ndarray) -> bytes:
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(16000)
        w.writeframes((np.clip(audio, -1, 1) * 32767).astype("<i2").tobytes())
    return buffer.getvalue()


def test_fbank_shape_and_mean_normalization():
    feats = kaldi_fbank(_tone(1.0))
    # snip_edges: 1 + (16000 - 400) // 160 tramas de 80 bandas
    assert feats.shape == (98, 80)
    assert feats.dtype == np.float32
    assert np.allclose(feats.mean(axis=0), 0, atol=1e-4)


def test_fbank_puts_energy_in_the_right_band():
    # La CMN resta la media por banda; con media frase de silencio, la banda
    # del tono sigue destacando en la parte con sonido.
    raw_low = kaldi_fbank(np.concatenate([_tone(1.0, 200), np.zeros(16000, np.float32)]))
    raw_high = kaldi_fbank(np.concatenate([_tone(1.0, 3000), np.zeros(16000, np.float32)]))
    assert raw_low[:90].mean(axis=0).argmax() < raw_high[:90].mean(axis=0).argmax()


def test_short_audio_has_no_features():
    assert kaldi_fbank(np.zeros(100, np.float32)).shape == (0, 80)


def test_cosine():
    a = np.array([1.0, 0.0])
    assert cosine(a, a) == pytest.approx(1.0)
    assert cosine(a, np.array([0.0, 1.0])) == pytest.approx(0.0)


class _FakeVerifier(SpeakerVerifier):
    """Huella = media del audio por bloques: determinista y sin modelo."""

    def __init__(self, profile_path: Path) -> None:
        super().__init__(model_path=Path(__file__), profile_path=profile_path)

    def embed(self, audio):
        if audio.size < 0.8 * 16000:
            return None
        spectrum = np.abs(np.fft.rfft(audio[:16000]))
        vector = np.array([band.sum() for band in np.array_split(spectrum, 32)])
        return vector / (np.linalg.norm(vector) + 1e-9)


def test_enroll_saves_only_a_vector_and_scores(tmp_path):
    verifier = _FakeVerifier(tmp_path / "profile.json")
    assert verifier.score(_tone(1.5)) is None, "sin voz registrada no hay puntuación"
    profile = verifier.enroll([_tone(1.5, seed=1), _tone(1.5, seed=2), _tone(1.5, seed=3)])
    assert profile["samples"] == 3
    saved = (tmp_path / "profile.json").read_text(encoding="utf-8")
    assert '"embedding"' in saved and "audio" not in saved
    same, other = verifier.score(_tone(1.5, seed=9)), verifier.score(_tone(1.5, freq=1800, seed=9))
    assert same > 0.9 and other < 0.6, (same, other)
    assert verifier.score(_tone(0.3)) is None, "demasiado corta para juzgar"
    verifier.delete()
    assert verifier.profile() is None


def test_enroll_needs_two_usable_samples(tmp_path):
    verifier = _FakeVerifier(tmp_path / "profile.json")
    with pytest.raises(ValueError):
        verifier.enroll([_tone(1.5), _tone(0.2)])


@pytest.mark.skipif(not MODEL.exists(), reason="modelo de huella de voz no descargado")
def test_real_model_tells_tones_apart(tmp_path):
    pytest.importorskip("onnxruntime")
    verifier = SpeakerVerifier(MODEL, tmp_path / "profile.json")
    embedding = verifier.embed(_tone(1.5))
    assert embedding is not None and embedding.shape == (256,)
    assert np.linalg.norm(embedding) == pytest.approx(1.0, abs=1e-6)


# ---------- API ----------


@pytest.fixture
def fake_verifier(tmp_path):
    from app.api.deps import get_speaker_verifier
    from app.main import app

    verifier = _FakeVerifier(tmp_path / "profile.json")
    app.dependency_overrides[get_speaker_verifier] = lambda: verifier
    yield verifier
    app.dependency_overrides.pop(get_speaker_verifier, None)


def test_speaker_enroll_status_and_delete(client, auth_headers, fake_verifier):
    assert client.get("/api/v1/voice/speaker", headers=auth_headers).json()["enrolled"] is False
    files = [("samples", (f"s{i}.wav", _wav(_tone(1.5, seed=i)), "audio/wav")) for i in range(3)]
    response = client.post("/api/v1/voice/speaker/enroll", files=files, headers=auth_headers)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["enrolled"] is True and body["samples"] == 3
    assert client.delete("/api/v1/voice/speaker", headers=auth_headers).json()["enrolled"] is False


def test_speaker_enroll_rejects_too_few_samples(client, auth_headers, fake_verifier):
    files = [("samples", ("s.wav", _wav(_tone(1.5)), "audio/wav"))]
    assert client.post("/api/v1/voice/speaker/enroll", files=files, headers=auth_headers).status_code == 422


def test_transcribe_returns_speaker_score_only_when_asked(client, auth_headers, fake_verifier):
    fake_verifier.enroll([_tone(1.5, seed=1), _tone(1.5, seed=2)])
    audio = {"audio": ("a.wav", _wav(_tone(1.5, seed=5)), "audio/wav")}
    plain = client.post("/api/v1/voice/transcribe", files=audio, headers=auth_headers).json()
    assert plain["speaker_score"] is None
    checked = client.post("/api/v1/voice/transcribe", params={"speaker": "true"}, files=audio, headers=auth_headers).json()
    assert checked["speaker_score"] > 0.9
    other = {"audio": ("b.wav", _wav(_tone(1.5, freq=1800)), "audio/wav")}
    assert client.post("/api/v1/voice/transcribe", params={"speaker": "true"}, files=other, headers=auth_headers).json()["speaker_score"] < 0.6


def test_other_voice_is_not_transcribed_when_speaker_min_is_set(client, auth_headers, fake_verifier):
    from app.api.deps import get_stt_provider
    from app.main import app
    from app.voice.mock_provider import MockSTTProvider

    calls = []

    class _CountingSTT(MockSTTProvider):
        def transcribe(self, audio_bytes, language=None, *, fast=False, prompt=None):
            calls.append(1)
            return "Atlas, hola"

    app.dependency_overrides[get_stt_provider] = lambda: _CountingSTT()
    try:
        fake_verifier.enroll([_tone(1.5, seed=1), _tone(1.5, seed=2)])
        other = {"audio": ("b.wav", _wav(_tone(1.5, freq=1800)), "audio/wav")}
        body = client.post("/api/v1/voice/transcribe", params={"speaker": "true", "speaker_min": 0.8}, files=other, headers=auth_headers).json()
        assert body["text"] == "" and body["speaker_score"] < 0.8
        assert calls == [], "Whisper no se ejecuta para otra voz"
        mine = {"audio": ("a.wav", _wav(_tone(1.5, seed=5)), "audio/wav")}
        body = client.post("/api/v1/voice/transcribe", params={"speaker": "true", "speaker_min": 0.8}, files=mine, headers=auth_headers).json()
        assert body["text"] == "Atlas, hola" and calls == [1]
    finally:
        app.dependency_overrides.pop(get_stt_provider, None)
