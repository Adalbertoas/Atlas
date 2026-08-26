"""VisionProvider real: Claude es multimodal, no hace falta un servicio de
visión aparte (ni un motor de OCR — Claude ya lee texto de una imagen como
parte de la misma respuesta, ver docs/architecture.md).
"""
from __future__ import annotations

import base64
import io

import anthropic
from PIL import Image

from app.vision.base import VisionProvider

_DEFAULT_QUESTION = (
    "Describí qué ves en esta imagen de forma clara y breve. Si hay texto legible "
    "(mensajes de error, ventanas, etc.), incluilo tal cual aparece."
)


class AnthropicVisionProvider(VisionProvider):
    def __init__(self, api_key: str, model: str, max_tokens: int = 1024) -> None:
        if not api_key:
            raise ValueError(
                "ANTHROPIC_API_KEY vacío. Configura tu key en .env o usa VISION_PROVIDER=mock."
            )
        self._client = anthropic.Anthropic(api_key=api_key)
        self._model = model
        self._max_tokens = max_tokens

    def analyze(self, image_bytes: bytes, question: str | None = None) -> str:
        # Normaliza a PNG: la imagen puede venir en cualquier formato (captura
        # de pantalla, foto del celular) y esto evita adivinar el media_type.
        image = Image.open(io.BytesIO(image_bytes))
        buffer = io.BytesIO()
        image.convert("RGB").save(buffer, format="PNG")
        encoded = base64.b64encode(buffer.getvalue()).decode("ascii")

        response = self._client.messages.create(
            model=self._model,
            max_tokens=self._max_tokens,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image",
                            "source": {"type": "base64", "media_type": "image/png", "data": encoded},
                        },
                        {"type": "text", "text": question or _DEFAULT_QUESTION},
                    ],
                }
            ],
        )
        return "\n".join(block.text for block in response.content if block.type == "text").strip()
