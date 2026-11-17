"""Descarga el modelo de huella de voz (WeSpeaker ResNet34, VoxCeleb, ONNX, 26 MB)
que usa "solo responder a mi voz". Se guarda en .cache/speaker/ del repositorio
(fuera de git) y se verifica su SHA-256.

    python scripts/download_speaker_model.py
"""
from __future__ import annotations

import hashlib
import sys
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.voice.speaker import SPEAKER_MODEL_FILE, SPEAKER_MODEL_SHA256, SPEAKER_MODEL_URL  # noqa: E402

TARGET = Path(__file__).resolve().parents[2] / ".cache" / "speaker" / SPEAKER_MODEL_FILE


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for block in iter(lambda: file.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def main() -> None:
    if TARGET.exists() and sha256(TARGET) == SPEAKER_MODEL_SHA256:
        print(f"Ya esta descargado: {TARGET}")
        return
    TARGET.parent.mkdir(parents=True, exist_ok=True)
    partial = TARGET.with_suffix(".part")
    print(f"Descargando {SPEAKER_MODEL_URL} ...")
    urllib.request.urlretrieve(SPEAKER_MODEL_URL, partial)
    if sha256(partial) != SPEAKER_MODEL_SHA256:
        partial.unlink(missing_ok=True)
        raise SystemExit("La descarga no coincide con el SHA-256 esperado; no se guardo.")
    partial.replace(TARGET)
    print(f"Listo: {TARGET}")


if __name__ == "__main__":
    main()
