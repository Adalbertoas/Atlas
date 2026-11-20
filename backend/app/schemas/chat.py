from __future__ import annotations

from pydantic import BaseModel, Field


class ChatAttachment(BaseModel):
    """Archivo adjunto al mensaje (imagen o PDF), en base64."""

    name: str = ""
    mime_type: str
    data: str


class ChatRequest(BaseModel):
    message: str = ""
    conversation_id: str | None = None
    attachments: list[ChatAttachment] = Field(default_factory=list)


class ChatImage(BaseModel):
    """Imagen devuelta por una tool (ej. un mapa de radar), en base64."""

    mime_type: str
    data: str


class ChatFile(BaseModel):
    """Archivo generado por una tool; se descarga por GET /api/v1/files/{name}."""

    name: str
    mime_type: str
    size: int
    path: str


class ChatResponse(BaseModel):
    reply: str | None = None
    conversation_id: str
    requires_confirmation: bool = False
    confirmation_id: str | None = None
    confirmation_description: str | None = None
    images: list[ChatImage] = []
    files: list[ChatFile] = []


class ConfirmRequest(BaseModel):
    confirmation_id: str
    approve: bool = True


class ConfirmResponse(BaseModel):
    reply: str
    images: list[ChatImage] = []
    files: list[ChatFile] = []
