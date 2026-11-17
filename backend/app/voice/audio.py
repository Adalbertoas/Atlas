"""Decodificación de audio a float32 mono a 16 kHz (lo que esperan Whisper y la
verificación de hablante)."""
from __future__ import annotations

import io
import wave

import numpy as np

SAMPLE_RATE = 16000


def pcm16_wav_to_float(audio_bytes: bytes) -> np.ndarray | None:
    """Decodifica un WAV PCM16 mono a 16 kHz (lo que manda el cliente
    Electron) directamente a float32, sin pasar por ffmpeg/PyAV. Devuelve
    None si el audio tiene otro formato y hay que usar el decodificador
    general."""
    try:
        with wave.open(io.BytesIO(audio_bytes), "rb") as wav:
            if wav.getnchannels() != 1 or wav.getsampwidth() != 2 or wav.getframerate() != SAMPLE_RATE:
                return None
            frames = wav.readframes(wav.getnframes())
    except (wave.Error, EOFError):
        return None
    return np.frombuffer(frames, dtype="<i2").astype(np.float32) / 32768.0


def decode_any_audio(audio_bytes: bytes) -> np.ndarray:
    """Decodifica cualquier formato (webm/opus del navegador, mp3, WAV a otra
    frecuencia...) a float32 mono a 16 kHz con PyAV.

    No se usa el decodificador de faster-whisper porque 1.2.1 llama a
    av.open(metadata_errors=...), argumento que PyAV 19 eliminó: con esa
    combinación toda transcripción de webm fallaba."""
    import av  # dependencia de faster-whisper; solo hace falta para formatos no-PCM

    resampler = av.AudioResampler(format="s16", layout="mono", rate=SAMPLE_RATE)
    chunks: list[np.ndarray] = []
    with av.open(io.BytesIO(audio_bytes), mode="r") as container:
        for frame in container.decode(audio=0):
            for out in resampler.resample(frame):
                chunks.append(out.to_ndarray().reshape(-1))
        for out in resampler.resample(None):  # vacía lo que quede en el resampler
            chunks.append(out.to_ndarray().reshape(-1))
    if not chunks:
        return np.zeros(0, dtype=np.float32)
    return np.concatenate(chunks).astype(np.float32) / 32768.0


def decode_audio(audio_bytes: bytes) -> np.ndarray:
    pcm = pcm16_wav_to_float(audio_bytes)
    return pcm if pcm is not None else decode_any_audio(audio_bytes)
