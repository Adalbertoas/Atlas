from __future__ import annotations

from fastapi import APIRouter, Form, UploadFile
from pydantic import BaseModel

from app.vision.provider_factory import get_vision_provider

router = APIRouter(prefix="/vision", tags=["vision"])


class AnalyzeResponse(BaseModel):
    description: str


@router.post("/analyze", response_model=AnalyzeResponse)
async def analyze(image: UploadFile, question: str | None = Form(None)) -> AnalyzeResponse:
    """Analiza una imagen ya subida por el usuario (ej. una foto sacada desde
    el celular) — directo, sin pasar por tool calling, porque el usuario ya
    decidió explícitamente compartir esa imagen (mismo criterio que
    /voice/transcribe)."""
    image_bytes = await image.read()
    provider = get_vision_provider()
    description = provider.analyze(image_bytes, question)
    return AnalyzeResponse(description=description)
