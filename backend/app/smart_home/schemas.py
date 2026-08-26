from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class RoomCreate(BaseModel):
    name: str


class RoomOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str


class DeviceOut(BaseModel):
    id: str
    name: str
    room: str | None
    type: str
    state: str
    capabilities: dict


class AssignRoomRequest(BaseModel):
    room_id: int | None  # null = quitar de cualquier habitación
