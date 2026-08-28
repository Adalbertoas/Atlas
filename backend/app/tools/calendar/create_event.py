from __future__ import annotations

from app.integrations.google_calendar import GoogleCalendarClient
from app.security.permissions import RiskLevel
from app.tools.base import Tool, ToolContext, ToolResult


class CreateCalendarEventTool(Tool):
    name = "create_calendar_event"
    description = (
        "Crea un evento en el Google Calendar del usuario. Usar cuando pide agendar algo "
        "('agendame una reunión mañana a las 15hs', 'poné en el calendario que tengo dentista "
        "el viernes'). Distinto de create_reminder: un evento de calendario queda visible en "
        "Google Calendar (y cualquier app que lo sincronice), un recordatorio solo vive en "
        "ATLAS. Las fechas deben resolverse a valores absolutos con get_current_time primero."
    )
    parameters = {
        "type": "object",
        "properties": {
            "summary": {"type": "string", "description": "Título del evento."},
            "start": {
                "type": "string",
                "description": "Inicio, ISO 8601 con offset, ej. '2026-08-29T15:00:00-03:00'.",
            },
            "end": {"type": "string", "description": "Fin, mismo formato que start."},
            "description": {"type": "string", "description": "Detalle opcional del evento."},
        },
        "required": ["summary", "start", "end"],
    }
    # LOW_RISK, no READ_ONLY: escribe en un calendario real (mismo criterio
    # que create_reminder) pero no tiene consecuencias irreversibles en el
    # mundo físico, así que no exige confirmación.
    risk_level = RiskLevel.LOW_RISK

    def __init__(self, client: GoogleCalendarClient) -> None:
        self._client = client

    def execute(self, params: dict, context: ToolContext) -> ToolResult:
        summary = (params.get("summary") or "").strip()
        start = (params.get("start") or "").strip()
        end = (params.get("end") or "").strip()
        if not summary or not start or not end:
            return ToolResult(success=False, error="Faltan 'summary', 'start' y/o 'end'.")

        try:
            event = self._client.create_event(
                summary=summary, start=start, end=end, description=params.get("description") or ""
            )
        except Exception as exc:  # noqa: BLE001
            return ToolResult(success=False, error=str(exc))

        return ToolResult(
            success=True,
            data=f"Evento creado: '{event.summary}' de {event.start} a {event.end}.",
        )
