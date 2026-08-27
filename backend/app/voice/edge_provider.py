"""TextToSpeechProvider con las voces neuronales de Edge (Fase 18).

Reemplaza a las voces SAPI de Windows, que suenan claramente sintéticas.
Edge TTS es el mismo motor que usa la función "leer en voz alta" del
navegador Edge: calidad neuronal, gratis y **sin API key**.

Compromisos que hay que tener presentes, porque no son obvios:

  · **Necesita internet.** SAPI funcionaba sin conexión; esto no. Si falla
    la red, la síntesis falla — por eso el endpoint de voz ya trata al
    audio como un extra y la respuesta de texto se muestra igual.
  · **El texto viaja a servidores de Microsoft.** Todo lo que ATLAS diga en
    voz alta sale de la máquina. Para uso local sin conexión está
    `TTS_PROVIDER=sapi`, que sigue disponible.
  · **Es una vía no oficial.** Microsoft no publica esta API para terceros;
    `edge-tts` la usa por ingeniería inversa y podría dejar de funcionar
    sin aviso. Por eso el proveedor viejo no se borró.

Edge devuelve MP3, pero la interfaz del proyecto (y el cliente de
escritorio, que reproduce con `soundfile`) esperan WAV. Se convierte acá
para que ningún cliente tenga que enterarse del cambio.
"""
from __future__ import annotations

import asyncio
import io
import logging

from app.voice.base import TextToSpeechProvider

logger = logging.getLogger(__name__)

# Voz por defecto si no se configura EDGE_TTS_VOICE. Elegida por el usuario
# tras comparar muestras de siete voces en español. La lista completa sale
# de `python -m edge_tts --list-voices`.
DEFAULT_VOICE = "es-MX-JorgeNeural"


class EdgeTTSProvider(TextToSpeechProvider):
    def __init__(self, voice: str = DEFAULT_VOICE, rate: str = "+0%", pitch: str = "+0Hz") -> None:
        self._voice = voice or DEFAULT_VOICE
        self._rate = rate
        self._pitch = pitch

    def synthesize(self, text: str) -> bytes:
        if not text or not text.strip():
            return b""

        mp3 = self._synthesize_mp3(text)
        return _mp3_to_wav(mp3)

    def _synthesize_mp3(self, text: str) -> bytes:
        import edge_tts

        async def run() -> bytes:
            communicate = edge_tts.Communicate(
                text, self._voice, rate=self._rate, pitch=self._pitch
            )
            chunks = bytearray()
            async for chunk in communicate.stream():
                if chunk["type"] == "audio":
                    chunks.extend(chunk["data"])
            return bytes(chunks)

        # El endpoint que llama a esto es síncrono (def, no async def), así
        # que FastAPI lo corre en un threadpool sin loop de asyncio propio.
        # asyncio.run() es correcto acá y no choca con el loop del servidor.
        return asyncio.run(run())


def _mp3_to_wav(mp3_bytes: bytes) -> bytes:
    """Edge devuelve MP3; el resto del proyecto habla WAV.

    soundfile lo soporta desde libsndfile 1.1 (acá hay 1.2.2), así que no
    hace falta ffmpeg ni ninguna dependencia externa.
    """
    import soundfile as sf

    data, sample_rate = sf.read(io.BytesIO(mp3_bytes), dtype="int16")
    buffer = io.BytesIO()
    sf.write(buffer, data, sample_rate, format="WAV", subtype="PCM_16")
    return buffer.getvalue()
