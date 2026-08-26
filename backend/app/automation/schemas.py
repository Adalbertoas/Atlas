from __future__ import annotations

from pydantic import BaseModel


class ActionCreate(BaseModel):
    tool_name: str
    params: dict = {}


class TriggerCreate(BaseModel):
    type: str  # "SCHEDULE" | "DEVICE_STATE"
    config: dict = {}


class RoutineCreate(BaseModel):
    name: str
    actions: list[ActionCreate] = []
    triggers: list[TriggerCreate] = []


class ActionOut(BaseModel):
    tool_name: str
    params: dict


class TriggerOut(BaseModel):
    type: str
    config: dict


class RoutineOut(BaseModel):
    id: int
    name: str
    actions: list[ActionOut]
    triggers: list[TriggerOut]


class RoutineRunResult(BaseModel):
    routine_name: str
    executed: list[str]
    skipped: list[str]
