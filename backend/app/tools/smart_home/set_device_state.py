"""set_device_state: enciende/apaga/ajusta un dispositivo (sección 9/10).

El riesgo real depende del TIPO de dispositivo (sección 5 del prompt
maestro: encender una luz es LOW_RISK, abrir una cerradura es CRITICAL,
acceder a una cámara es HIGH_RISK) — por eso esta tool sobreescribe
`resolve_risk_level` en vez de usar un único `risk_level` fijo.
"""
from __future__ import annotations

from app.events.bus import Event, EventBus, EventType
from app.security.permissions import RiskLevel
from app.smart_home.base import DeviceType, SmartDevice, SmartHomeProvider
from app.tools.base import Tool, ToolContext, ToolResult

_RISK_BY_TYPE: dict[DeviceType, RiskLevel] = {
    DeviceType.LOCK: RiskLevel.CRITICAL,
    DeviceType.CAMERA: RiskLevel.HIGH_RISK,
}
_DEFAULT_RISK = RiskLevel.LOW_RISK  # luces, enchufes, switches, fan, TV, termostato/climate


def _find_device(provider: SmartHomeProvider, query: str) -> SmartDevice | None:
    query = (query or "").strip().lower()
    if not query:
        return None
    devices = provider.list_devices()
    for d in devices:
        if d.id.lower() == query:
            return d
    for d in devices:
        if query in d.name.lower():
            return d
    return None


class SetDeviceStateTool(Tool):
    name = "set_device_state"
    description = (
        "Cambia el estado de un dispositivo smart home: encender/apagar, subir/bajar temperatura, "
        "brillo, o bloquear/desbloquear una cerradura."
    )
    parameters = {
        "type": "object",
        "properties": {
            "device": {"type": "string", "description": "Nombre o id del dispositivo, ej. 'Luz Sala'."},
            "action": {
                "type": "string",
                "description": "turn_on | turn_off | lock | unlock | set_temperature | set_brightness",
            },
            "value": {"type": "number", "description": "Valor para set_temperature/set_brightness."},
        },
        "required": ["device", "action"],
    }
    risk_level = _DEFAULT_RISK  # fallback si algo llama al atributo estático directamente

    def __init__(self, provider: SmartHomeProvider, events: EventBus) -> None:
        self._provider = provider
        self._events = events

    def resolve_risk_level(self, params: dict) -> RiskLevel:
        device = _find_device(self._provider, str(params.get("device", "")))
        if device is None:
            # No se pudo verificar qué es: por seguridad, pedir confirmación
            # en vez de asumir que es de bajo riesgo.
            return RiskLevel.MEDIUM_RISK
        return _RISK_BY_TYPE.get(device.type, _DEFAULT_RISK)

    def human_description(self, params: dict) -> str:
        return f"{params.get('action', '?')} en el dispositivo '{params.get('device', '?')}'"

    def execute(self, params: dict, context: ToolContext) -> ToolResult:
        device = _find_device(self._provider, str(params.get("device", "")))
        if device is None:
            return ToolResult(success=False, error=f"No encontré el dispositivo '{params.get('device')}'.")

        action = str(params.get("action", "")).strip()
        if device.type == DeviceType.SENSOR:
            return ToolResult(success=False, error=f"'{device.name}' es un sensor de solo lectura.")

        try:
            updated = self._provider.set_state(device.id, action, params.get("value"))
        except (ValueError, KeyError) as exc:
            return ToolResult(success=False, error=str(exc))

        self._events.publish(
            Event(
                type=EventType.DEVICE_STATE_CHANGED,
                payload={"device_id": updated.id, "state": updated.state},
            )
        )
        return ToolResult(success=True, data=f"{updated.name} ahora está: {updated.state}.")
