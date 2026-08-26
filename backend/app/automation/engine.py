"""Conecta los triggers DEVICE_STATE al Event Bus (sección 11).

Los triggers SCHEDULE se resuelven aparte, en app/automation/scheduler.py
(necesitan un reloj, no un evento).
"""
from __future__ import annotations

import json

from app.automation import service
from app.automation.models import Routine, RoutineTrigger
from app.core.database import SessionLocal
from app.events.bus import Event, EventBus, EventType
from app.tools.registry import ToolRegistry

# Protección básica contra recursión: si ejecutar una rutina cambia el
# estado de un dispositivo que dispara ESA MISMA rutina de nuevo, esto evita
# un loop infinito (no detecta ciclos más largos, pero cubre el caso obvio).
_running_routines: set[int] = set()


def register_device_state_triggers(registry: ToolRegistry, events: EventBus) -> None:
    def handler(event: Event) -> None:
        device_id = event.payload.get("device_id")
        state = event.payload.get("state")
        if device_id is None:
            return

        db = SessionLocal()
        try:
            triggers = db.query(RoutineTrigger).filter(RoutineTrigger.type == "DEVICE_STATE").all()
            for trigger in triggers:
                config = json.loads(trigger.config_json)
                if config.get("device_id") != device_id or config.get("state") != state:
                    continue
                if trigger.routine_id in _running_routines:
                    continue

                routine = db.get(Routine, trigger.routine_id)
                if routine is None:
                    continue

                _running_routines.add(trigger.routine_id)
                try:
                    service.execute_routine(db, routine, registry, events)
                finally:
                    _running_routines.discard(trigger.routine_id)
        finally:
            db.close()

    events.subscribe(EventType.DEVICE_STATE_CHANGED, handler)
