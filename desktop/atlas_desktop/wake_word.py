"""Escucha continua con palabra de activación "Atlas" (modo Wake Word).

No usa un motor de wake-word dedicado (Porcupine necesita cuenta/licencia;
openWakeWord no trae un modelo en español para "Atlas" listo para usar).
En cambio, reutiliza el Whisper local que ya expone el backend
(/api/v1/voice/transcribe): mantiene un buffer de audio deslizante (no
bloques fijos pegados uno tras otro — así "Atlas" nunca queda cortado justo
en el límite entre dos grabaciones), se salta las ventanas en silencio
(filtro de energía, barato y local) y solo transcribe las que tienen sonido
real, buscando "atlas" en el texto resultante.

Limitación conocida: más lento y menos preciso que un motor de wake-word
dedicado (~1-3s de latencia), y puede confundir "Atlas" con palabras
parecidas. Es la versión V1.
"""
from __future__ import annotations

import io
import re
import threading
import time
from collections import deque
from collections.abc import Callable

import numpy as np
import sounddevice as sd
import soundfile as sf

from atlas_desktop import api_client

SAMPLE_RATE = 16000
BUFFER_SECONDS = 3.0  # ventana deslizante que se revisa en busca de la palabra de activación
POLL_INTERVAL_SECONDS = 1.0  # cada cuánto se revisa el buffer
SILENCE_RMS_THRESHOLD = 1000.0  # audio int16. Ajustado tras probar en vivo: el ruido
# ambiente típico de una habitación ya llega a ~800 de RMS y disparaba
# transcripciones falsas (Whisper "alucina" frases sobre ruido de fondo).
# Puede necesitar más ajuste según el micrófono/ambiente de cada quien.


def has_speech(chunk: np.ndarray, threshold: float = SILENCE_RMS_THRESHOLD) -> bool:
    """True si el segmento tiene energía suficiente para valer la pena transcribirlo."""
    if chunk.size == 0:
        return False
    rms = float(np.sqrt(np.mean(np.square(chunk.astype(np.float64)))))
    return rms >= threshold


def contains_wake_word(text: str, wake_word: str = "atlas") -> bool:
    """True solo si "atlas" aparece entre las primeras palabras del texto —
    como cuando alguien te llama por tu nombre al empezar a hablarte. Antes
    se buscaba en cualquier parte del texto, lo que disparaba falsos
    positivos con conversaciones de fondo que mencionaban "atlas" de pasada
    a mitad de una frase que no era para ATLAS."""
    words = re.findall(r"[a-záéíóúñ]+", (text or "").lower())
    leading_words = words[:2]
    return wake_word.lower() in leading_words


def to_wav_bytes(audio: np.ndarray, sample_rate: int = SAMPLE_RATE) -> bytes:
    buffer = io.BytesIO()
    sf.write(buffer, audio, sample_rate, format="WAV", subtype="PCM_16")
    return buffer.getvalue()


def _record_chunk(seconds: float, sample_rate: int = SAMPLE_RATE) -> np.ndarray:
    audio = sd.rec(int(seconds * sample_rate), samplerate=sample_rate, channels=1, dtype="int16")
    sd.wait()
    return audio.reshape(-1)


def record_command_until_silence(
    max_seconds: float = 8.0,
    trailing_silence_chunks: int = 2,
    chunk_seconds: float = 1.0,
    sample_rate: int = SAMPLE_RATE,
) -> np.ndarray:
    """Graba el comando después de detectar la palabra de activación: sigue
    grabando mientras haya voz, y corta tras un par de segundos de silencio
    (o al llegar a max_seconds, lo que pase primero)."""
    frames: list[np.ndarray] = []
    started_speaking = False
    silence_streak = 0
    elapsed = 0.0

    while elapsed < max_seconds:
        chunk = _record_chunk(chunk_seconds, sample_rate)
        elapsed += chunk_seconds
        if has_speech(chunk):
            started_speaking = True
            silence_streak = 0
            frames.append(chunk)
        elif started_speaking:
            silence_streak += 1
            frames.append(chunk)
            if silence_streak >= trailing_silence_chunks:
                break

    if not frames:
        return np.array([], dtype=np.int16)
    return np.concatenate(frames)


class WakeWordListener:
    """Mantiene el micrófono abierto en un InputStream continuo (buffer
    deslizante), revisando cada POLL_INTERVAL_SECONDS si hay sonido y, si lo
    hay, transcribiéndolo para buscar la palabra de activación.

    Mientras on_activated() está corriendo, el stream de audio se detiene y
    el buffer se vacía — así ATLAS no puede captar su propia voz por los
    parlantes (eco) mientras responde.
    """

    def __init__(self, on_activated: Callable[[], None], wake_word: str = "atlas") -> None:
        self._on_activated = on_activated
        self._wake_word = wake_word
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._stream: sd.InputStream | None = None
        self._buffer: deque[np.int16] = deque(maxlen=int(BUFFER_SECONDS * SAMPLE_RATE))
        self._buffer_lock = threading.Lock()

    def start(self) -> None:
        if self._thread is not None:
            return
        self._stop_event.clear()
        try:
            self._open_stream()
        except Exception as exc:  # noqa: BLE001 — no tirar la app si no hay micrófono disponible
            print(f"[wake_word] no se pudo abrir el micrófono: {exc!r}")
            return
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        self._close_stream()
        self._thread = None

    @property
    def is_active(self) -> bool:
        return self._thread is not None

    def _open_stream(self) -> None:
        with self._buffer_lock:
            self._buffer.clear()
        self._stream = sd.InputStream(
            samplerate=SAMPLE_RATE, channels=1, dtype="int16", callback=self._on_audio_block
        )
        self._stream.start()

    def _close_stream(self) -> None:
        if self._stream is not None:
            self._stream.stop()
            self._stream.close()
            self._stream = None

    def _on_audio_block(self, indata, _frames, _time_info, _status) -> None:
        with self._buffer_lock:
            self._buffer.extend(indata.reshape(-1))

    def _snapshot_buffer(self) -> np.ndarray:
        with self._buffer_lock:
            return np.array(self._buffer, dtype=np.int16)

    def _run(self) -> None:
        while not self._stop_event.is_set():
            try:
                self._poll_once()
            except Exception as exc:  # noqa: BLE001 — el loop de escucha NUNCA debe morir en silencio
                print(f"[wake_word] error inesperado en el loop, sigo escuchando: {exc!r}", flush=True)
                time.sleep(1)

    def _poll_once(self) -> None:
        time.sleep(POLL_INTERVAL_SECONDS)
        if self._stop_event.is_set():
            return

        snapshot = self._snapshot_buffer()
        if not has_speech(snapshot):
            return

        try:
            text = api_client.transcribe_audio(to_wav_bytes(snapshot))
        except Exception:  # noqa: BLE001 — un fallo de transcripción no debe matar el loop
            return

        if not contains_wake_word(text, self._wake_word):
            return

        # Palabra detectada: pausar la captura (evita eco mientras ATLAS
        # responde) y correr el callback, que es deliberadamente bloqueante
        # — ver docstring de la clase.
        self._close_stream()
        try:
            self._on_activated()
        finally:
            if not self._stop_event.is_set():
                self._open_stream()
