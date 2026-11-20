"""VisionProvider real: Claude es multimodal, no hace falta un servicio de
visión aparte (ni un motor de OCR — Claude ya lee texto de una imagen como
parte de la misma respuesta, ver docs/architecture.md).
"""
from __future__ import annotations

import anthropic

from app.vision.base import VisionProvider

_DEFAULT_QUESTION = (
    "Describí qué ves en esta imagen de forma clara y breve. Si hay texto legible "
    "(mensajes de error, ventanas, etc.), incluilo tal cual aparece."
)


class AnthropicVisionProvider(VisionProvider):
    def __init__(self, api_key: str, model: str, max_tokens: int = 4096) -> None:
        if not api_key:
            raise ValueError(
                "ANTHROPIC_API_KEY vacío. Configura tu key en .env o usa VISION_PROVIDER=mock."
            )
        self._client = anthropic.Anthropic(api_key=api_key)
        self._model = model
        self._max_tokens = max_tokens

    def analyze(self, image_bytes: bytes, question: str | None = None) -> str:
        # La imagen puede venir en cualquier formato y tamaño (captura de dos
        # monitores, foto del celular): se acota a lo que acepta la API.
        from app.core.attachments import normalize_image_bytes

        media_type, encoded = normalize_image_bytes(image_bytes, "imagen")

        response = self._client.messages.create(
            model=self._model,
            max_tokens=self._max_tokens,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image",
                            "source": {"type": "base64", "media_type": media_type, "data": encoded},
                        },
                        {"type": "text", "text": question or _DEFAULT_QUESTION},
                    ],
                }
            ],
        )
        return "\n".join(block.text for block in response.content if block.type == "text").strip()
