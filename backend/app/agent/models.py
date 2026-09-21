"""Modelos estructurados de planificación y ejecución del agente."""
from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, Field


class TaskStatus(str, Enum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    WAITING_CONFIRMATION = "WAITING_CONFIRMATION"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class AgentGoal(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    description: str = Field(min_length=1, max_length=4000)
    status: TaskStatus = TaskStatus.PENDING
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class TaskStep(BaseModel):
    id: str
    description: str
    target_type: Literal["tool", "skill", "analysis"]
    target_id: str | None = None
    parameters: dict[str, Any] = Field(default_factory=dict)
    status: TaskStatus = TaskStatus.PENDING
    result: Any = None
    error: str | None = None


class TaskPlan(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    goal: AgentGoal
    steps: list[TaskStep] = Field(default_factory=list)
    status: TaskStatus = TaskStatus.PENDING
    current_step: int = 0
    tool_calls: int = 0
    failure_reason: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    started_at: datetime | None = None
    completed_at: datetime | None = None


class TaskResult(BaseModel):
    plan_id: str
    status: TaskStatus
    summary: str
    steps: list[TaskStep]
    confirmation_id: str | None = None
    confirmation_description: str | None = None
