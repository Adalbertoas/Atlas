"""Triggers SCHEDULE: tarea en background que revisa la hora cada
CHECK_INTERVAL_SECONDS y dispara las rutinas que correspondan (sección 11)."""
from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime

from app.automation import service
from app.automation.models import Routine, RoutineTrigger
from app.core.database import SessionLocal
from app.events.bus import EventBus
from app.tools.registry import ToolRegistry

logger = logging.getLogger(__name__)

CHECK_INTERVAL_SECONDS = 30


class AutomationScheduler:
    def __init__(self, registry: ToolRegistry, events: EventBus) -> None:
        self._registry = registry
        self._events = events
        self._task: asyncio.Task | None = None
        self._stop_event = asyncio.Event()
        # trigger.id -> "HH:MM" del último disparo, para no repetir dos
        # veces dentro del mismo minuto (el loop revisa cada 30s).
        self._last_fired: dict[int, str] = {}

    def start(self) -> None:
        self._stop_event.clear()
        self._task = asyncio.create_task(self._loop())

    async def stop(self) -> None:
        self._stop_event.set()
        if self._task is not None:
            try:
                await asyncio.wait_for(self._task, timeout=5)
            except (asyncio.TimeoutError, asyncio.CancelledError):
                self._task.cancel()
            self._task = None

    async def _loop(self) -> None:
        while not self._stop_event.is_set():
            try:
                await asyncio.wait_for(self._stop_event.wait(), timeout=CHECK_INTERVAL_SECONDS)
            except asyncio.TimeoutError:
                pass  # timeout normal: toca revisar los triggers
            if self._stop_event.is_set():
                return
            self._check_triggers()

    def _check_triggers(self) -> None:
        now_hhmm = datetime.now().strftime("%H:%M")
        db = SessionLocal()
        try:
            triggers = db.query(RoutineTrigger).filter(RoutineTrigger.type == "SCHEDULE").all()
            for trigger in triggers:
                config = json.loads(trigger.config_json)
                if config.get("time") != now_hhmm:
                    continue
                if self._last_fired.get(trigger.id) == now_hhmm:
                    continue
                self._last_fired[trigger.id] = now_hhmm

                routine = db.get(Routine, trigger.routine_id)
                if routine is None:
                    continue
                try:
                    service.execute_routine(db, routine, self._registry, self._events)
                except Exception:  # noqa: BLE001 — un fallo en una rutina no debe tumbar el scheduler
                    logger.exception("Error ejecutando la rutina '%s' por trigger de horario", routine.name)
        finally:
            db.close()
