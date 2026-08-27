"""Avisos de recordatorios vencidos (Fase 20).

Hueco que dejó la Fase 11: se podían crear recordatorios, listarlos y
pedírselos a ATLAS por voz, pero **nada revisaba si vencían**. Un
recordatorio que no interrumpe no sirve para nada.

Sigue el mismo patrón que AutomationScheduler: una tarea en background que
revisa cada CHECK_INTERVAL_SECONDS. Al vencer uno, emite
NOTIFICATION_CREATED — el subscriber de notificaciones ya existente lo
persiste, y de ahí lo levantan los tres clientes.
"""
from __future__ import annotations

import logging
import asyncio
from datetime import datetime

from app.core.database import SessionLocal
from app.events.bus import Event, EventBus, EventType
from app.reminders.models import Reminder

logger = logging.getLogger(__name__)

CHECK_INTERVAL_SECONDS = 30


class ReminderScheduler:
    def __init__(self, events: EventBus) -> None:
        self._events = events
        self._task: asyncio.Task | None = None
        self._stop_event = asyncio.Event()

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
                pass  # timeout normal: toca revisar los recordatorios
            if self._stop_event.is_set():
                return
            try:
                self.check_due()
            except Exception:  # noqa: BLE001 — el scheduler NUNCA debe morir en silencio
                logger.exception("Error revisando recordatorios vencidos")

    def check_due(self) -> int:
        """Notifica los recordatorios vencidos y los marca. Devuelve cuántos.

        Público (no `_check_due`) para poder ejercitarlo desde los tests sin
        depender del reloj del loop.
        """
        db = SessionLocal()
        try:
            due = (
                db.query(Reminder)
                .filter(
                    Reminder.done.is_(False),
                    Reminder.notified.is_(False),
                    Reminder.due_at <= datetime.now(),
                )
                .all()
            )
            for reminder in due:
                # Se marca ANTES de emitir: si el subscriber falla, es
                # preferible perder un aviso a repetirlo cada 30 segundos
                # para siempre.
                reminder.notified = True
                db.commit()
                self._events.publish(
                    Event(
                        type=EventType.NOTIFICATION_CREATED,
                        payload={"reminder": reminder.text, "due_at": reminder.due_at.isoformat()},
                    )
                )
                logger.info("Recordatorio vencido notificado: %s", reminder.text)
            return len(due)
        finally:
            db.close()
