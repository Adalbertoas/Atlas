from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class NotificationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    message: str
    read: bool
    created_at: datetime


class PushSubscriptionKeys(BaseModel):
    p256dh: str
    auth: str


class PushSubscriptionIn(BaseModel):
    """Forma exacta que devuelve PushSubscription.toJSON() en el navegador —
    se recibe tal cual, sin transformarla, para no depender de que el
    cliente arme un payload distinto."""

    endpoint: str
    keys: PushSubscriptionKeys
