from __future__ import annotations

from app.security.permissions import RiskLevel
from app.smart_home import service
from app.smart_home.base import SmartHomeProvider
from app.tools.base import Tool, ToolContext, ToolResult


class ListDevicesTool(Tool):
    name = "list_devices"
    description = "Lista los dispositivos smart home, opcionalmente filtrados por habitación o tipo."
    parameters = {
        "type": "object",
        "properties": {
            "room": {"type": "string", "description": "Filtrar por habitación, ej. 'Oficina'."},
            "type": {
                "type": "string",
                "description": "Filtrar por tipo: LIGHT, SWITCH, PLUG, SENSOR, THERMOSTAT, TV, LOCK, CAMERA, FAN, CLIMATE.",
            },
        },
        "required": [],
    }
    risk_level = RiskLevel.READ_ONLY

    def __init__(self, provider: SmartHomeProvider) -> None:
        self._provider = provider

    def execute(self, params: dict, context: ToolContext) -> ToolResult:
        try:
            devices = service.list_devices(
                context.db, self._provider, room=params.get("room"), device_type=params.get("type")
            )
        except Exception as exc:  # noqa: BLE001
            return ToolResult(success=False, error=str(exc))

        if not devices:
            return ToolResult(success=True, data="No encontré dispositivos con esos filtros.")

        summary = "; ".join(
            f"{d.name} ({d.type.value}, {d.room or 'sin habitación'}): {d.state}" for d in devices
        )
        return ToolResult(success=True, data=summary)
