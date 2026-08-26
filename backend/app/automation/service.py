"""Automation Engine: CRUD de rutinas + ejecución (sección 11).

Regla de seguridad no negociable (sección 5): una rutina JAMÁS ejecuta una
acción cuyo riesgo real (resolve_risk_level) requiera confirmación — sin
importar si la disparó un horario, un dispositivo, o el propio usuario por
voz en el momento. Esas acciones se saltan y se notifica por qué (evento
NOTIFICATION_CREATED) en vez de pedir confirmación a nadie: no hay nadie
necesariamente presente para responderla.
"""
from __future__ import annotations

import json

from sqlalchemy.orm import Session

from app.automation.models import Routine, RoutineAction, RoutineTrigger
from app.automation.schemas import RoutineCreate, RoutineOut, RoutineRunResult
from app.events.bus import Event, EventBus, EventType
from app.security.permissions import AUTO_APPROVE_LEVELS
from app.tools.base import ToolContext
from app.tools.registry import ToolRegistry


def _to_out(db: Session, routine: Routine) -> RoutineOut:
    actions = (
        db.query(RoutineAction)
        .filter(RoutineAction.routine_id == routine.id)
        .order_by(RoutineAction.order)
        .all()
    )
    triggers = db.query(RoutineTrigger).filter(RoutineTrigger.routine_id == routine.id).all()
    return RoutineOut(
        id=routine.id,
        name=routine.name,
        actions=[{"tool_name": a.tool_name, "params": json.loads(a.params_json)} for a in actions],
        triggers=[{"type": t.type, "config": json.loads(t.config_json)} for t in triggers],
    )


def list_routines(db: Session) -> list[RoutineOut]:
    return [_to_out(db, r) for r in db.query(Routine).order_by(Routine.name).all()]


def get_routine_by_name(db: Session, name: str) -> Routine | None:
    return db.query(Routine).filter(Routine.name.ilike(name)).first()


def create_routine(db: Session, data: RoutineCreate) -> RoutineOut:
    routine = Routine(name=data.name)
    db.add(routine)
    db.flush()  # asigna routine.id sin cerrar la transacción

    for i, action in enumerate(data.actions):
        db.add(
            RoutineAction(
                routine_id=routine.id,
                tool_name=action.tool_name,
                params_json=json.dumps(action.params, ensure_ascii=False),
                order=i,
            )
        )
    for trigger in data.triggers:
        db.add(
            RoutineTrigger(
                routine_id=routine.id,
                type=trigger.type,
                config_json=json.dumps(trigger.config, ensure_ascii=False),
            )
        )

    db.commit()
    db.refresh(routine)
    return _to_out(db, routine)


def delete_routine(db: Session, routine_id: int) -> bool:
    routine = db.get(Routine, routine_id)
    if routine is None:
        return False
    db.query(RoutineAction).filter(RoutineAction.routine_id == routine_id).delete()
    db.query(RoutineTrigger).filter(RoutineTrigger.routine_id == routine_id).delete()
    db.delete(routine)
    db.commit()
    return True


def execute_routine(
    db: Session, routine: Routine, registry: ToolRegistry, events: EventBus
) -> RoutineRunResult:
    events.publish(Event(type=EventType.AUTOMATION_TRIGGERED, payload={"routine": routine.name}))

    actions = (
        db.query(RoutineAction)
        .filter(RoutineAction.routine_id == routine.id)
        .order_by(RoutineAction.order)
        .all()
    )

    executed: list[str] = []
    skipped: list[str] = []

    for action in actions:
        tool = registry.get(action.tool_name)
        params = json.loads(action.params_json)

        if tool is None:
            skipped.append(f"{action.tool_name} (herramienta no encontrada)")
            continue

        risk = tool.resolve_risk_level(params)
        if risk not in AUTO_APPROVE_LEVELS:
            reason = f"'{action.tool_name}' requiere confirmación ({risk.value}) y las rutinas nunca la piden solas."
            skipped.append(f"{action.tool_name} ({risk.value})")
            events.publish(
                Event(
                    type=EventType.NOTIFICATION_CREATED,
                    payload={"routine": routine.name, "tool_name": action.tool_name, "reason": reason},
                )
            )
            continue

        result = tool.execute(params, ToolContext(db=db))
        executed.append(f"{action.tool_name}: {result.as_text()}")

    events.publish(
        Event(
            type=EventType.AUTOMATION_COMPLETED,
            payload={"routine": routine.name, "executed": len(executed), "skipped": len(skipped)},
        )
    )

    return RoutineRunResult(routine_name=routine.name, executed=executed, skipped=skipped)
