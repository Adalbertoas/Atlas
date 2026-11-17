"""Crear imágenes y dibujos y guardarlos en la galería. Lo usan tanto las tools
del chat como la API del Estudio creativo, para que ambos caminos den lo mismo."""
from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache

from app.ai.base import AIProvider
from app.creative import gallery, images, svg


class CreativeError(Exception):
    """Error legible para el usuario."""


@dataclass
class CreationResult:
    creation: gallery.Creation
    data: bytes


def create_image(prompt: str, engine: str | None = None, aspect: str | None = None, style: str | None = None, seed: int | None = None) -> CreationResult:
    try:
        image = images.generate(prompt, engine=engine, aspect=aspect, style=style, seed=seed)
    except images.ImageEngineError as exc:
        raise CreativeError(str(exc)) from exc
    creation = gallery.save(image.data, image.mime_type, image.engine, prompt.strip(), image.width, image.height)
    return CreationResult(creation=creation, data=image.data)


@lru_cache
def _drawing_provider() -> AIProvider:
    from app.ai.factory import build_ai_provider
    from app.config import get_settings

    settings = get_settings()
    model = settings.creative_model if settings.ai_provider == "anthropic" else None
    # Un SVG detallado ocupa miles de tokens (más el razonamiento del modelo).
    return build_ai_provider(model=model or None, max_tokens=16000)


def create_vector(description: str, aspect: str | None = None, provider: AIProvider | None = None) -> CreationResult:
    try:
        drawing = svg.draw(provider or _drawing_provider(), description, aspect)
    except svg.SvgError as exc:
        raise CreativeError(str(exc)) from exc
    except Exception as exc:  # noqa: BLE001 — fallo del proveedor de IA (red, clave, límite)
        raise CreativeError(f"No pude dibujar ahora mismo ({exc.__class__.__name__}).") from exc
    data = drawing.encode("utf-8")
    width, height = svg.svg_size(drawing)
    creation = gallery.save(data, "image/svg+xml", "claude", description.strip(), width, height)
    return CreationResult(creation=creation, data=data)


ENHANCE_PROMPT = (
    "Eres director de arte. Convierte la idea del usuario en UN prompt para un generador de imágenes: "
    "en inglés, una sola línea de 40 a 90 palabras, concreto y visual (sujeto, acción, entorno, estilo, "
    "iluminación, encuadre, paleta, atmósfera). Respeta la intención y cualquier detalle pedido; no "
    "agregues texto escrito dentro de la imagen salvo que se pida. Responde solo con el prompt."
)


@lru_cache
def _enhance_provider() -> AIProvider:
    from app.ai.factory import build_ai_provider

    return build_ai_provider(max_tokens=2000)


def enhance_prompt(idea: str, provider: AIProvider | None = None) -> str:
    """Reescribe una idea corta (en cualquier idioma) como prompt detallado en inglés."""
    from app.ai.base import AIMessage

    idea = (idea or "").strip()
    if len(idea) < 3:
        raise CreativeError("Escribe primero una idea para la imagen.")
    try:
        response = (provider or _enhance_provider()).chat(
            [AIMessage(role="system", content=ENHANCE_PROMPT), AIMessage(role="user", content=idea)]
        )
    except Exception as exc:  # noqa: BLE001
        raise CreativeError(f"No pude mejorar el prompt ahora mismo ({exc.__class__.__name__}).") from exc
    text = " ".join((response.text or "").split()).strip().strip('"')
    if not text:
        raise CreativeError("La IA no devolvió un prompt.")
    return text[:3000]
