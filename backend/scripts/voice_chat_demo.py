"""Demo por consola: habla con ATLAS usando el micrófono y los parlantes.

No es el cliente final (ese es el cliente de Windows, Fase 4) — es solo para
probar el pipeline de voz completo ahora mismo:
    Micrófono -> /voice/transcribe -> /chat -> /voice/speak -> parlantes

Requiere:
- El servidor ATLAS corriendo (`python run.py`).
- STT_PROVIDER=whisper y TTS_PROVIDER=sapi en .env (si no, transcribe/habla
  con las respuestas simuladas del modo mock).

Uso:
    python scripts/voice_chat_demo.py
    (Enter para empezar a grabar, Enter de nuevo para terminar. Ctrl+C para salir.)
"""
from __future__ import annotations

import io
import sys

import numpy as np
import requests
import sounddevice as sd
import soundfile as sf

ATLAS_URL = "http://127.0.0.1:8000"
SAMPLE_RATE = 16000


def record_audio() -> bytes:
    print("🎙️  Grabando... presiona Enter para terminar.")
    frames: list[np.ndarray] = []

    def callback(indata, _frame_count, _time_info, _status) -> None:
        frames.append(indata.copy())

    with sd.InputStream(samplerate=SAMPLE_RATE, channels=1, dtype="int16", callback=callback):
        input()

    if not frames:
        return b""
    audio = np.concatenate(frames, axis=0)
    buffer = io.BytesIO()
    sf.write(buffer, audio, SAMPLE_RATE, format="WAV", subtype="PCM_16")
    return buffer.getvalue()


def play_audio(wav_bytes: bytes) -> None:
    data, sample_rate = sf.read(io.BytesIO(wav_bytes), dtype="int16")
    sd.play(data, sample_rate)
    sd.wait()


def main() -> None:
    conversation_id: str | None = None
    print("ATLAS — demo de voz. Ctrl+C para salir.\n")

    while True:
        try:
            input("Presiona Enter para hablarle a ATLAS...")
        except (KeyboardInterrupt, EOFError):
            print("\nHasta luego.")
            sys.exit(0)

        audio_bytes = record_audio()
        if not audio_bytes:
            continue

        transcribe_resp = requests.post(
            f"{ATLAS_URL}/api/v1/voice/transcribe",
            files={"audio": ("audio.wav", audio_bytes, "audio/wav")},
            timeout=60,
        )
        transcribe_resp.raise_for_status()
        text = transcribe_resp.json()["text"]
        print(f"Tú: {text}")
        if not text.strip():
            continue

        chat_resp = requests.post(
            f"{ATLAS_URL}/api/v1/chat",
            json={"message": text, "conversation_id": conversation_id},
            timeout=60,
        )
        chat_resp.raise_for_status()
        chat_body = chat_resp.json()
        conversation_id = chat_body["conversation_id"]

        if chat_body["requires_confirmation"]:
            print(f"ATLAS: {chat_body['confirmation_description']} — confirmar? (esta demo no confirma acciones)")
            continue

        reply = chat_body["reply"] or ""
        print(f"ATLAS: {reply}")

        speak_resp = requests.post(f"{ATLAS_URL}/api/v1/voice/speak", json={"text": reply}, timeout=60)
        speak_resp.raise_for_status()
        play_audio(speak_resp.content)


if __name__ == "__main__":
    main()
