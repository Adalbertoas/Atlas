"""Motores de imágenes realistas o artísticas (fotos, cuadros, conceptos).

- OpenAI (gpt-image): alta calidad, de pago, necesita OPENAI_API_KEY.
- Pollinations: gratis y sin clave; el prompt viaja a pollinations.ai y la
  imagen sale con su marca de agua.

Ambos se llaman por HTTP con httpx, sin SDK: así no se suma otra dependencia
y ningún módulo fuera de app/ai importa un SDK de IA.
"""
from __future__ import annotations

import base64
import random
from dataclasses import dataclass
from urllib.parse import quote

import httpx

from app.config import get_settings

ENGINES = ("openai", "pollinations")

# Formato → tamaño. OpenAI solo acepta estos tres; Pollinations acepta cualquiera.
ASPECTS: dict[str, tuple[int, int]] = {
    "cuadrado": (1024, 1024),
    "horizontal": (1536, 1024),
    "vertical": (1024, 1536),
}

# Estilos predefinidos: se agregan al final del prompt.
STYLES: dict[str, str] = {
    "foto": "photorealistic photograph, natural lighting, sharp focus, high detail",
    "cine": "cinematic film still, dramatic lighting, shallow depth of field, anamorphic",
    "ilustracion": "detailed digital illustration, vibrant colors, clean lines",
    "anime": "anime style, cel shading, expressive, studio quality",
    "acuarela": "watercolor painting, soft washes, paper texture",
    "oleo": "oil painting, visible brush strokes, rich texture, classical composition",
    "3d": "3D render, octane render, soft global illumination, studio lighting",
    "pixel": "pixel art, 16-bit, crisp pixels, limited palette",
    "boceto": "pencil sketch, graphite shading, hand drawn on paper",
    "neon": "cyberpunk neon, glowing lights, dark atmosphere, futuristic",
}

_TIMEOUT = httpx.Timeout(150.0, connect=15.0)


class ImageEngineError(Exception):
    """Fallo legible para el usuario (sin clave, servicio caído, contenido rechazado...)."""


@dataclass
class GeneratedImage:
    data: bytes
    mime_type: str
    engine: str
    prompt: str
    width: int
    height: int

    @property
    def base64(self) -> str:
        return base64.b64encode(self.data).decode("ascii")


def available_engines() -> list[str]:
    settings = get_settings()
    if not settings.web_enabled:
        return []
    return [e for e in ENGINES if e != "openai" or settings.openai_api_key]


def resolve_engine(engine: str | None) -> str:
    """'auto' (o vacío) → el motor por defecto: OpenAI si hay clave, si no Pollinations."""
    settings = get_settings()
    if not settings.web_enabled:
        raise ImageEngineError("El acceso a internet está desactivado (WEB_ENABLED=false); no puedo generar imágenes.")
    choice = (engine or "auto").strip().lower()
    if choice == "auto":
        choice = (settings.image_default_engine or "auto").strip().lower()
    if choice == "auto":
        choice = "openai" if settings.openai_api_key else "pollinations"
    if choice not in ENGINES:
        raise ImageEngineError(f"Motor de imágenes desconocido: '{engine}'. Usa openai o pollinations.")
    if choice == "openai" and not settings.openai_api_key:
        raise ImageEngineError(
            "OpenAI no está configurado: agrega OPENAI_API_KEY en backend/.env y reinicia ATLAS. "
            "Mientras tanto puedo usar Pollinations, que es gratis."
        )
    return choice


def build_prompt(prompt: str, style: str | None) -> str:
    prompt = " ".join(prompt.split())
    extra = STYLES.get((style or "").strip().lower())
    return f"{prompt}, {extra}" if extra else prompt


def generate(prompt: str, engine: str | None = None, aspect: str | None = None, style: str | None = None, seed: int | None = None) -> GeneratedImage:
    prompt = (prompt or "").strip()
    if len(prompt) < 3:
        raise ImageEngineError("Describe la imagen que quieres (al menos unas palabras).")
    if len(prompt) > 3000:
        raise ImageEngineError("La descripción es demasiado larga (máximo 3000 caracteres).")
    width, height = ASPECTS.get((aspect or "cuadrado").strip().lower(), ASPECTS["cuadrado"])
    full_prompt = build_prompt(prompt, style)
    chosen = resolve_engine(engine)
    if chosen == "openai":
        return _openai(full_prompt, width, height)
    return _pollinations(full_prompt, width, height, seed)


def _pollinations(prompt: str, width: int, height: int, seed: int | None) -> GeneratedImage:
    url = f"https://image.pollinations.ai/prompt/{quote(prompt, safe='')}"
    params = {"width": width, "height": height, "seed": seed if seed is not None else random.randint(1, 2**31 - 1), "nologo": "true", "model": "flux"}
    try:
        response = httpx.get(url, params=params, timeout=_TIMEOUT, follow_redirects=True)
    except httpx.TimeoutException as exc:
        raise ImageEngineError("Pollinations tardó demasiado en responder. Intenta de nuevo en un momento.") from exc
    except httpx.HTTPError as exc:
        raise ImageEngineError(f"No pude conectar con Pollinations ({exc.__class__.__name__}).") from exc
    mime = response.headers.get("content-type", "").split(";")[0].strip()
    if response.status_code == 429:
        raise ImageEngineError("Pollinations está limitando las peticiones (demasiadas seguidas). Espera unos segundos.")
    if response.status_code != 200 or not mime.startswith("image/"):
        raise ImageEngineError(f"Pollinations no devolvió una imagen (HTTP {response.status_code}).")
    return GeneratedImage(data=response.content, mime_type=mime, engine="pollinations", prompt=prompt, width=width, height=height)


def _openai(prompt: str, width: int, height: int) -> GeneratedImage:
    settings = get_settings()
    quality = settings.openai_image_quality if settings.openai_image_quality in ("low", "medium", "high") else "medium"
    body = {"model": settings.openai_image_model, "prompt": prompt, "size": f"{width}x{height}", "quality": quality, "n": 1}
    try:
        response = httpx.post(
            "https://api.openai.com/v1/images/generations",
            json=body,
            headers={"Authorization": f"Bearer {settings.openai_api_key}"},
            timeout=_TIMEOUT,
        )
    except httpx.TimeoutException as exc:
        raise ImageEngineError("OpenAI tardó demasiado en generar la imagen. Intenta de nuevo.") from exc
    except httpx.HTTPError as exc:
        raise ImageEngineError(f"No pude conectar con OpenAI ({exc.__class__.__name__}).") from exc
    try:
        payload = response.json()
    except ValueError:
        payload = {}
    if response.status_code != 200:
        message = (payload.get("error") or {}).get("message") if isinstance(payload, dict) else None
        if response.status_code == 401:
            raise ImageEngineError("OpenAI rechazó la clave (OPENAI_API_KEY inválida o revocada).")
        if response.status_code == 429:
            raise ImageEngineError("OpenAI: límite de uso o saldo agotado. Revisa tu cuenta de OpenAI.")
        raise ImageEngineError(f"OpenAI no generó la imagen: {message or f'HTTP {response.status_code}'}")
    try:
        data = base64.b64decode(payload["data"][0]["b64_json"])
    except (KeyError, IndexError, TypeError, ValueError) as exc:
        raise ImageEngineError("OpenAI respondió sin imagen.") from exc
    return GeneratedImage(data=data, mime_type="image/png", engine="openai", prompt=prompt, width=width, height=height)
