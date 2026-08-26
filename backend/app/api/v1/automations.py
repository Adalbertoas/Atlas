from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.deps import get_db_session
from app.automation import service
from app.automation.models import Routine
from app.automation.schemas import RoutineCreate, RoutineOut, RoutineRunResult
from app.events.bus import event_bus
from app.tools.registry import tool_registry

router = APIRouter(prefix="/automations", tags=["automations"])


@router.get("", response_model=list[RoutineOut])
def list_automations(db: Session = Depends(get_db_session)) -> list[RoutineOut]:
    return service.list_routines(db)


@router.post("", response_model=RoutineOut)
def create_automation(body: RoutineCreate, db: Session = Depends(get_db_session)) -> RoutineOut:
    return service.create_routine(db, body)


@router.post("/{routine_id}/run", response_model=RoutineRunResult)
def run_automation(routine_id: int, db: Session = Depends(get_db_session)) -> RoutineRunResult:
    routine = db.get(Routine, routine_id)
    if routine is None:
        raise HTTPException(status_code=404, detail="Rutina no encontrada.")
    return service.execute_routine(db, routine, tool_registry, event_bus)


@router.delete("/{routine_id}")
def delete_automation(routine_id: int, db: Session = Depends(get_db_session)) -> dict:
    ok = service.delete_routine(db, routine_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Rutina no encontrada.")
    return {"deleted": True}
