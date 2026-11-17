"""Estudio creativo: generar imágenes y dibujos sin pasar por el chat, y la galería."""
from __future__ import annotations

import base64

from fastapi import APIRouter, HTTPException
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, Field

from app.config import get_settings
from app.creative import gallery, images
from app.creative.service import CreationResult, CreativeError, create_image, create_vector, enhance_prompt

router = APIRouter(prefix="/creative", tags=["creative"])


class ImageRequest(BaseModel):
    prompt: str = Field(min_length=3, max_length=3000)
    engine: str = "auto"  # auto | openai | pollinations | claude (vectorial)
    style: str = ""
    aspect: str = "cuadrado"


class EnhanceRequest(BaseModel):
    prompt: str = Field(min_length=3, max_length=2000)


def _meta(creation: gallery.Creation) -> dict:
    return {
        "id": creation.id,
        "mime_type": creation.mime_type,
        "engine": creation.engine,
        "prompt": creation.prompt,
        "width": creation.width,
        "height": creation.height,
        "created_at": creation.created_at,
        "path": str(gallery.path_of(creation)),
    }


def _creation_out(creation: gallery.Creation, data: bytes | None = None) -> dict:
    payload = data if data is not None else gallery.read(creation)
    return {**_meta(creation), "data": base64.b64encode(payload).decode("ascii")}


@router.get("/engines")
def engines() -> dict:
    settings = get_settings()
    available = images.available_engines()
    if settings.ai_provider == "anthropic":
        available.append("claude")
    return {
        "available": available,
        "default": images.resolve_engine("auto") if images.available_engines() else None,
        "styles": sorted(images.STYLES),
        "aspects": list(images.ASPECTS),
        "folder": str(gallery.creations_dir()),
    }


@router.post("/image")
async def generate(request: ImageRequest) -> dict:
    def work() -> CreationResult:
        if request.engine == "claude":
            prompt = f"{request.prompt}. Estilo: {request.style}" if request.style else request.prompt
            return create_vector(prompt, aspect=request.aspect)
        return create_image(request.prompt, engine=request.engine, aspect=request.aspect, style=request.style)

    try:
        result = await run_in_threadpool(work)
    except CreativeError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return _creation_out(result.creation, result.data)


@router.post("/enhance")
async def enhance(request: EnhanceRequest) -> dict:
    try:
        return {"prompt": await run_in_threadpool(enhance_prompt, request.prompt)}
    except CreativeError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/gallery")
def list_gallery(limit: int = 12) -> list[dict]:
    """Miniaturas (livianas); la imagen completa se pide por id."""
    items = []
    for creation in gallery.recent(max(1, min(limit, 48))):
        try:
            thumb, mime = gallery.thumbnail(creation)
        except (OSError, ValueError):
            continue
        items.append({**_meta(creation), "thumb": base64.b64encode(thumb).decode("ascii"), "thumb_mime": mime})
    return items


@router.get("/gallery/{creation_id}")
def get_creation(creation_id: str) -> dict:
    creation = gallery.get(creation_id)
    if creation is None:
        raise HTTPException(status_code=404, detail="Esa creación no existe.")
    return _creation_out(creation)


@router.delete("/gallery/{creation_id}")
def delete_creation(creation_id: str) -> dict:
    if not gallery.delete(creation_id):
        raise HTTPException(status_code=404, detail="Esa creación no existe.")
    return {"deleted": creation_id}
