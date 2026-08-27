"""Estado en vivo del control por gestos (Fase 13).

El WebSocket de gestos no dejaba rastro consultable: se sabía si un celular
estaba controlando el mouse solo mirando si el cursor se movía. El
dashboard corre en la PC controlada (la cámara está en el celular), así que
lo único que puede mostrar con honestidad es *el estado del receptor* — y
para eso hace falta registrarlo.

Estado en memoria de proceso, no en base: es efímero por definición (muere
con la conexión) y ATLAS es de un solo usuario, así que una sesión a la vez
alcanza. Mismo criterio que el token del cliente de escritorio.
"""
from __future__ import annotations

import threading
from dataclasses import dataclass
from datetime import datetime, timezone


@dataclass
class GestureState:
    connected: bool = False
    connected_since: datetime | None = None
    last_event_at: datetime | None = None
    events_received: int = 0


class GestureSessionTracker:
    """Thread-safe: el handler del WebSocket corre en el loop de asyncio y
    el endpoint REST que lo lee puede atenderse en otro hilo."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._state = GestureState()

    def connected(self) -> None:
        with self._lock:
            now = datetime.now(timezone.utc)
            self._state = GestureState(connected=True, connected_since=now, last_event_at=None)

    def record_event(self) -> None:
        with self._lock:
            self._state.last_event_at = datetime.now(timezone.utc)
            self._state.events_received += 1

    def disconnected(self) -> None:
        with self._lock:
            self._state.connected = False

    def snapshot(self) -> GestureState:
        with self._lock:
            # Copia: quien lo lea no debe poder mutar el estado compartido.
            return GestureState(
                connected=self._state.connected,
                connected_since=self._state.connected_since,
                last_event_at=self._state.last_event_at,
                events_received=self._state.events_received,
            )


# Instancia única de proceso, igual que tool_registry / event_bus.
gesture_session = GestureSessionTracker()
