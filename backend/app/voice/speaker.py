"""Verificación de hablante: ¿esta frase la dijo el usuario registrado?

Huella de voz con WeSpeaker ResNet34 (VoxCeleb, ONNX, 256 dimensiones) sobre
onnxruntime, que ya viene con faster-whisper: no hace falta PyTorch. El modelo
espera un banco de filtros Mel estilo Kaldi (el de torchaudio.compliance.kaldi),
reimplementado aquí en numpy.

Todo es local: el audio no sale del equipo y la huella se guarda como un
vector en un archivo JSON (no se guarda audio).
"""
from __future__ import annotations

import json
import threading
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

SAMPLE_RATE = 16000
FRAME_LENGTH = 400  # 25 ms
FRAME_SHIFT = 160  # 10 ms
FFT_SIZE = 512
MEL_BINS = 80
LOW_FREQ = 20.0
# Por debajo de esto la huella no es fiable (medido con voces sintéticas: con
# menos de ~0,8 s las puntuaciones de la misma voz caen mucho).
MIN_SECONDS = 0.8
SPEAKER_MODEL_FILE = "voxceleb_resnet34_LM.onnx"
SPEAKER_MODEL_URL = f"https://huggingface.co/Wespeaker/wespeaker-voxceleb-resnet34-LM/resolve/main/{SPEAKER_MODEL_FILE}"
SPEAKER_MODEL_SHA256 = "7bb2f06e9df17cdf1ef14ee8a15ab08ed28e8d0ef5054ee135741560df2ec068"


def _mel(freq: np.ndarray | float) -> np.ndarray | float:
    return 1127.0 * np.log(1.0 + np.asarray(freq) / 700.0)


def _mel_banks() -> np.ndarray:
    """Filtros triangulares en escala Mel, como Kaldi (sin el bin de Nyquist)."""
    num_fft_bins = FFT_SIZE // 2
    fft_bin_width = SAMPLE_RATE / FFT_SIZE
    mel_low, mel_high = _mel(LOW_FREQ), _mel(SAMPLE_RATE / 2)
    delta = (mel_high - mel_low) / (MEL_BINS + 1)
    bin_mels = _mel(fft_bin_width * np.arange(num_fft_bins))
    banks = np.zeros((MEL_BINS, num_fft_bins + 1))
    for m in range(MEL_BINS):
        left, center, right = mel_low + m * delta, mel_low + (m + 1) * delta, mel_low + (m + 2) * delta
        up = (bin_mels - left) / (center - left)
        down = (right - bin_mels) / (right - center)
        banks[m, :num_fft_bins] = np.maximum(0.0, np.minimum(up, down))
    return banks


_BANKS = _mel_banks()
_WINDOW = (0.5 - 0.5 * np.cos(2 * np.pi * np.arange(FRAME_LENGTH) / (FRAME_LENGTH - 1))) ** 0.85  # "povey"


def kaldi_fbank(audio: np.ndarray) -> np.ndarray:
    """log-Mel fbank (T, 80) con los valores por defecto de WeSpeaker: 25/10 ms,
    sin dither, preénfasis 0,97, ventana povey, potencia, y media restada (CMN)."""
    # WeSpeaker escala la onda a enteros de 16 bits antes del fbank.
    samples = np.asarray(audio, dtype=np.float64) * (1 << 15)
    if samples.size < FRAME_LENGTH:
        return np.zeros((0, MEL_BINS), dtype=np.float32)
    count = 1 + (samples.size - FRAME_LENGTH) // FRAME_SHIFT
    index = np.arange(FRAME_LENGTH)[None, :] + FRAME_SHIFT * np.arange(count)[:, None]
    frames = samples[index]
    frames = frames - frames.mean(axis=1, keepdims=True)
    emphasized = frames.copy()
    emphasized[:, 1:] -= 0.97 * frames[:, :-1]
    emphasized[:, 0] -= 0.97 * frames[:, 0]
    power = np.abs(np.fft.rfft(emphasized * _WINDOW, n=FFT_SIZE)) ** 2
    feats = np.log(np.maximum(power @ _BANKS.T, np.finfo(np.float32).eps))
    feats -= feats.mean(axis=0, keepdims=True)
    return feats.astype(np.float32)


def cosine(a: np.ndarray, b: np.ndarray) -> float:
    return float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b) + 1e-9))


class SpeakerVerifier:
    def __init__(self, model_path: Path, profile_path: Path) -> None:
        self._model_path = model_path
        self._profile_path = profile_path
        self._session = None
        self._lock = threading.Lock()

    @property
    def available(self) -> bool:
        return self._model_path.exists()

    def embed(self, audio: np.ndarray) -> np.ndarray | None:
        """Huella normalizada de un audio float32 a 16 kHz, o None si es muy corto."""
        if audio.size < MIN_SECONDS * SAMPLE_RATE:
            return None
        feats = kaldi_fbank(audio)
        with self._lock:
            if self._session is None:
                import onnxruntime  # perezoso: solo se carga si se usa la verificación

                self._session = onnxruntime.InferenceSession(str(self._model_path), providers=["CPUExecutionProvider"])
            (embedding,) = self._session.run(None, {"feats": feats[None]})
        vector = embedding[0].astype(np.float64)
        return vector / (np.linalg.norm(vector) + 1e-9)

    # ---------- Perfil ----------

    def profile(self) -> dict | None:
        try:
            data = json.loads(self._profile_path.read_text(encoding="utf-8"))
            return data if isinstance(data.get("embedding"), list) else None
        except (OSError, ValueError):
            return None

    def enroll(self, samples: list[np.ndarray]) -> dict:
        """Registra la voz a partir de varias frases. Devuelve el perfil guardado
        con la coherencia entre muestras (si es baja, alguna frase salió mal)."""
        embeddings = [e for e in (self.embed(s) for s in samples) if e is not None]
        if len(embeddings) < 2:
            raise ValueError("Hacen falta al menos 2 frases de mas de un segundo.")
        mean = np.mean(embeddings, axis=0)
        mean /= np.linalg.norm(mean) + 1e-9
        consistency = min(cosine(e, mean) for e in embeddings)
        profile = {
            "model": self._model_path.stem,
            "embedding": [round(float(v), 6) for v in mean],
            "samples": len(embeddings),
            "consistency": round(consistency, 3),
            "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        }
        self._profile_path.parent.mkdir(parents=True, exist_ok=True)
        self._profile_path.write_text(json.dumps(profile), encoding="utf-8")
        return profile

    def delete(self) -> None:
        self._profile_path.unlink(missing_ok=True)

    def score(self, audio: np.ndarray) -> float | None:
        """Similitud (coseno, -1..1) con la voz registrada, o None si no hay voz
        registrada o la frase es demasiado corta para juzgarla. Medido con voces
        sintéticas: la misma voz da 0,72–0,91 y otras voces hasta 0,46."""
        profile = self.profile()
        if profile is None:
            return None
        embedding = self.embed(audio)
        if embedding is None:
            return None
        return round(cosine(embedding, np.asarray(profile["embedding"])), 3)
