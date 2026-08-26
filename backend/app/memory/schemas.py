from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class MemoryCreate(BaseModel):
    content: str
    category: str = "personal"
    tags: list[str] = []


class MemoryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    category: str
    content: str
    tags: list[str]
    created_at: datetime
