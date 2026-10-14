from __future__ import annotations

from pydantic import BaseModel


class ChatRequest(BaseModel):
    message: str
    conversation_id: str | None = None


class ChatImage(BaseModel):
    """Imagen devuelta por una tool (ej. un mapa de radar), en base64."""

    mime_type: str
    data: str


class ChatResponse(BaseModel):
    reply: str | None = None
    conversation_id: str
    requires_confirmation: bool = False
    confirmation_id: str | None = None
    confirmation_description: str | None = None
    images: list[ChatImage] = []


class ConfirmRequest(BaseModel):
    confirmation_id: str
    approve: bool = True


class ConfirmResponse(BaseModel):
    reply: str
    images: list[ChatImage] = []
