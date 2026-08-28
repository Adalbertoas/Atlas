from __future__ import annotations

from app.integrations.google_calendar import GoogleCalendarClient
from app.security.permissions import RiskLevel
from app.tools.base import Tool, ToolContext, ToolResult


class ListCalendarEventsTool(Tool):
    name = "list_calendar_events"
    description = (
        "Lista los eventos del Google Calendar del usuario entre dos fechas/horas. "
        "Usar para responder '¿qué tengo hoy?', '¿tengo algo mañana?', '¿cuándo es mi próxima "
        "reunión?'. Los rangos deben resolverse a fechas absolutas — si el usuario dice 'hoy' "
        "o 'esta semana', calcular el rango con get_current_time primero."
    )
    parameters = {
        "type": "object",
        "properties": {
            "time_min": {
                "type": "string",
                "description": "Inicio del rango, ISO 8601 con offset, ej. '2026-08-28T00:00:00-03:00'.",
            },
            "time_max": {
                "type": "string",
                "description": "Fin del rango, mismo formato que time_min.",
            },
        },
        "required": ["time_min", "time_max"],
    }
    risk_level = RiskLevel.READ_ONLY

    def __init__(self, client: GoogleCalendarClient) -> None:
        self._client = client

    def execute(self, params: dict, context: ToolContext) -> ToolResult:
        time_min = (params.get("time_min") or "").strip()
        time_max = (params.get("time_max") or "").strip()
        if not time_min or not time_max:
            return ToolResult(success=False, error="Faltan 'time_min' y/o 'time_max'.")

        try:
            events = self._client.list_events(time_min, time_max)
        except Exception as exc:  # noqa: BLE001
            return ToolResult(success=False, error=str(exc))

        if not events:
            return ToolResult(success=True, data="No hay eventos en ese rango.")

        summary = "; ".join(f"{e.summary} ({e.start} a {e.end})" for e in events)
        return ToolResult(success=True, data=summary)
