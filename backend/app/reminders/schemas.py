from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class ReminderCreate(BaseModel):
    text: str
    due_at: datetime


class ReminderOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    text: str
    due_at: datetime
    done: bool
    created_at: datetime
