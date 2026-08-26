from __future__ import annotations

from app.vision.base import VisionProvider


class MockVisionProvider(VisionProvider):
    def analyze(self, image_bytes: bytes, question: str | None = None) -> str:
        return (
            "descripción simulada de la imagen "
            f"({len(image_bytes)} bytes) — configura VISION_PROVIDER=anthropic para análisis real."
        )
