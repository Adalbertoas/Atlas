"""TextToSpeechProvider usando las voces de Windows (SAPI) vía pyttsx3.

Gratis, sin internet, usa lo que ya tiene instalado Windows.
"""
from __future__ import annotations

import os
import tempfile

import pyttsx3

from app.voice.base import TextToSpeechProvider

# Idiomas preferidos, en orden. Si Windows tiene instalada una voz en
# español, se usa automáticamente — si no, cae en la voz por defecto del
# sistema (que puede leer texto en español con acento/pronunciación de
# inglés: es una limitación de qué voces tiene instaladas Windows, no de
# ATLAS. Ver docs/pending-manual-tests.md sobre cómo instalar una voz en
# español).
_PREFERRED_LANGUAGE_HINTS = ("es-", "spanish", "español")


def _pick_voice_id(engine: pyttsx3.Engine) -> str | None:
    for voice in engine.getProperty("voices"):
        haystack = f"{voice.id} {voice.name} {getattr(voice, 'languages', '')}".lower()
        if any(hint in haystack for hint in _PREFERRED_LANGUAGE_HINTS):
            return voice.id
    return None


class WindowsSapiProvider(TextToSpeechProvider):
    def synthesize(self, text: str) -> bytes:
        # pyttsx3 (driver SAPI5) no soporta síntesis a memoria directamente,
        # así que se escribe a un archivo temporal y se lee de vuelta.
        fd, path = tempfile.mkstemp(suffix=".wav")
        os.close(fd)
        try:
            engine = pyttsx3.init()
            spanish_voice_id = _pick_voice_id(engine)
            if spanish_voice_id:
                engine.setProperty("voice", spanish_voice_id)
            engine.save_to_file(text, path)
            engine.runAndWait()
            with open(path, "rb") as f:
                return f.read()
        finally:
            try:
                os.remove(path)
            except OSError:
                pass
