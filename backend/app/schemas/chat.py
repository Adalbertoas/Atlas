from __future__ import annotations

from pydantic import BaseModel


class ChatRequest(BaseModel):
    message: str
    conversation_id: str | None = None


class ChatResponse(BaseModel):
    reply: str | None = None
    conversation_id: str
    requires_confirmation: bool = False
    confirmation_id: str | None = None
    confirmation_description: str | None = None


class ConfirmRequest(BaseModel):
    confirmation_id: str
    approve: bool = True


class ConfirmResponse(BaseModel):
    reply: str
