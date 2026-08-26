"""control_room: acción masiva sobre una habitación (sección 10).

"Apaga todo en la oficina" solo afecta tipos seguros (ROOM_BULK_SAFE_TYPES:
luces, switches, enchufes, ventiladores, TV) — nunca cerraduras, cámaras,
sensores ni climatización en bloque, sin importar el resultado de la
confirmación. Por eso el riesgo siempre puede quedar en LOW_RISK: la propia
tool ya excluye cualquier dispositivo peligroso antes de tocarlo.
"""
from __future__ import annotations

from app.events.bus import Event, EventBus, EventType
from app.security.permissions import RiskLevel
from app.smart_home import service
from app.smart_home.base import ROOM_BULK_SAFE_TYPES, SmartHomeProvider
from app.tools.base import Tool, ToolContext, ToolResult

_ACTION_MAP = {"turn_on": "turn_on", "turn_off": "turn_off"}


class ControlRoomTool(Tool):
    name = "control_room"
    description = (
        "Enciende o apaga todos los dispositivos seguros (luces, enchufes, switches, ventiladores, TV) "
        "de una habitación. No afecta cerraduras, cámaras, sensores ni climatización."
    )
    parameters = {
        "type": "object",
        "properties": {
            "room": {"type": "string", "description": "Nombre de la habitación, ej. 'Oficina'."},
            "action": {"type": "string", "description": "turn_on | turn_off"},
        },
        "required": ["room", "action"],
    }
    risk_level = RiskLevel.LOW_RISK  # la tool ya restringe a tipos seguros; nunca toca Lock/Camera/Sensor/Climate

    def __init__(self, provider: SmartHomeProvider, events: EventBus) -> None:
        self._provider = provider
        self._events = events

    def human_description(self, params: dict) -> str:
        return f"{params.get('action', '?')} todos los dispositivos seguros de '{params.get('room', '?')}'"

    def execute(self, params: dict, context: ToolContext) -> ToolResult:
        room = str(params.get("room", "")).strip()
        action = _ACTION_MAP.get(str(params.get("action", "")).strip())
        if not room:
            return ToolResult(success=False, error="El parámetro 'room' no puede estar vacío.")
        if action is None:
            return ToolResult(success=False, error="Acción inválida: usa 'turn_on' o 'turn_off'.")

        devices = service.list_devices(context.db, self._provider, room=room)
        safe_devices = [d for d in devices if d.type in ROOM_BULK_SAFE_TYPES]

        if not safe_devices:
            return ToolResult(success=True, data=f"No hay dispositivos controlables en '{room}'.")

        affected, failed = [], []
        for device in safe_devices:
            try:
                updated = self._provider.set_state(device.id, action)
                affected.append(device.name)
                self._events.publish(
                    Event(
                        type=EventType.DEVICE_STATE_CHANGED,
                        payload={"device_id": updated.id, "state": updated.state},
                    )
                )
            except Exception as exc:  # noqa: BLE001
                failed.append(f"{device.name} ({exc})")

        summary = f"{action} aplicado a: {', '.join(affected)}."
        if failed:
            summary += f" Fallaron: {', '.join(failed)}."
        return ToolResult(success=True, data=summary)
