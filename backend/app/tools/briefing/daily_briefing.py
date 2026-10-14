"""daily_briefing: resumen del día (app/briefing/service.py)."""
from __future__ import annotations

from app.briefing.service import build_briefing
from app.events.bus import EventBus
from app.notifications.service import notify
from app.security.permissions import RiskLevel
from app.tools.base import Tool, ToolContext, ToolResult
from app.world.client import GodsEyeClient


class DailyBriefingTool(Tool):
    name = "daily_briefing"
    description = (
        "Arma el briefing del día: fecha, clima en casa, recordatorios de hoy, rutinas programadas, "
        "notificaciones sin leer, alertas activas y datos de la memoria. Usala cuando el usuario pida "
        "un resumen del día, 'qué tengo hoy' o 'buen día'."
    )
    parameters = {
        "type": "object",
        "properties": {
            "deliver": {
                "type": "boolean",
                "description": "true para dejarlo además como notificación (lo usa la rutina programada).",
            }
        },
        "required": [],
    }
    risk_level = RiskLevel.READ_ONLY

    def __init__(self, client: GodsEyeClient | None, home_place: str, events: EventBus) -> None:
        self._client = client
        self._home_place = home_place
        self._events = events

    def execute(self, params: dict, context: ToolContext) -> ToolResult:
        try:
            text = build_briefing(context.db, self._client, self._home_place)
        except Exception as exc:  # noqa: BLE001
            return ToolResult(success=False, error=f"No pude armar el briefing: {exc}")
        if params.get("deliver"):
            notify(self._events, f"☀️ {text}")
        return ToolResult(success=True, data=text)
