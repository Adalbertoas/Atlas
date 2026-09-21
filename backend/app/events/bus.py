"""Event Bus interno de ATLAS (sección 15 del prompt maestro).

Permite que el sistema crezca (Automation Engine, Smart Home, notificaciones)
sin acoplarse al Orchestrator: los módulos futuros se suscriben a eventos en
vez de que el Orchestrator los conozca directamente.

V1/Fase 2: implementación síncrona en memoria de proceso. Si el sistema
escala a múltiples workers, esto migra a pub/sub sobre Redis sin cambiar la
interfaz pública (subscribe/publish).
"""
from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


class EventType(str, Enum):
    DEVICE_STATE_CHANGED = "DEVICE_STATE_CHANGED"
    USER_COMMAND = "USER_COMMAND"
    AUTOMATION_TRIGGERED = "AUTOMATION_TRIGGERED"
    AUTOMATION_COMPLETED = "AUTOMATION_COMPLETED"
    VOICE_COMMAND_RECEIVED = "VOICE_COMMAND_RECEIVED"
    NOTIFICATION_CREATED = "NOTIFICATION_CREATED"
    SYSTEM_ALERT = "SYSTEM_ALERT"
    AGENT_TASK_STARTED = "AGENT_TASK_STARTED"
    AGENT_STEP_COMPLETED = "AGENT_STEP_COMPLETED"
    AGENT_TASK_COMPLETED = "AGENT_TASK_COMPLETED"
    AGENT_TASK_FAILED = "AGENT_TASK_FAILED"


@dataclass
class Event:
    type: EventType
    payload: dict[str, Any] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


EventHandler = Callable[[Event], None]


class EventBus:
    def __init__(self) -> None:
        self._subscribers: dict[EventType, list[EventHandler]] = {}

    def subscribe(self, event_type: EventType, handler: EventHandler) -> None:
        self._subscribers.setdefault(event_type, []).append(handler)

    def publish(self, event: Event) -> None:
        for handler in self._subscribers.get(event.type, []):
            try:
                handler(event)
            except Exception:  # noqa: BLE001 — un subscriber roto no debe tumbar el flujo principal
                logger.exception("Error en subscriber de evento %s", event.type)


def _log_subscriber(event: Event) -> None:
    logger.info("EVENT %s | %s", event.type.value, event.payload)


# Instancia única a nivel de proceso, inyectada vía app.api.deps / app.main.
event_bus = EventBus()


def register_default_subscribers() -> None:
    """Suscriptor mínimo (logging) para demostrar el bus mientras no existan
    consumidores reales (Automation Engine / Smart Home llegan en Fase 5-6)."""
    for event_type in EventType:
        event_bus.subscribe(event_type, _log_subscriber)
