from __future__ import annotations

from app.voice.base import VoiceActivationProvider, VoiceMode


class PushToTalkProvider(VoiceActivationProvider):
    """El cliente decide cuándo grabar/enviar audio (botón, tecla, etc.).
    El servidor no necesita hacer nada especial: siempre está "activo" para
    recibir lo que le manden a /voice/transcribe."""

    mode = VoiceMode.PUSH_TO_TALK

    def is_active(self) -> bool:
        return True
