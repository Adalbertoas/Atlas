from __future__ import annotations

from pydantic import BaseModel, Field
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.agent.models import TaskPlan, TaskResult
from app.agent.service import AgentService
from app.api.deps import get_agent_service, get_db_session

router = APIRouter(prefix="/agent", tags=["agent"])


class AgentGoalRequest(BaseModel):
    goal: str = Field(min_length=1, max_length=4000)


class AgentConfirmRequest(BaseModel):
    confirmation_id: str
    approve: bool


@router.post("/tasks", response_model=TaskResult)
def start_task(body: AgentGoalRequest, db: Session = Depends(get_db_session), service: AgentService = Depends(get_agent_service)) -> TaskResult:
    return service.start(db, body.goal)


@router.get("/tasks/{plan_id}", response_model=TaskPlan)
def get_task(plan_id: str, service: AgentService = Depends(get_agent_service)) -> TaskPlan:
    plan = service.get_plan(plan_id)
    if plan is None:
        raise HTTPException(status_code=404, detail="Tarea no encontrada o expirada.")
    return plan


@router.post("/tasks/{plan_id}/confirm", response_model=TaskResult)
def confirm_task(plan_id: str, body: AgentConfirmRequest, db: Session = Depends(get_db_session), service: AgentService = Depends(get_agent_service)) -> TaskResult:
    result = service.confirm(db, plan_id, body.confirmation_id, body.approve)
    if result is None:
        raise HTTPException(status_code=404, detail="Confirmación no encontrada o no corresponde a esta tarea.")
    return result
