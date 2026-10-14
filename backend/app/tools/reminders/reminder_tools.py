"""Tools de recordatorios y temporizadores (app/reminders/service.py)."""
from __future__ import annotations

from datetime import datetime

from app.reminders import service
from app.security.permissions import RiskLevel
from app.tools.base import Tool, ToolContext, ToolResult


class CreateReminderTool(Tool):
    name = "create_reminder"
    description = (
        "Crea un recordatorio o temporizador: ATLAS notifica el mensaje cuando llega el momento. "
        "Para 'en 20 minutos' usá in_minutes; para una hora usá at ('HH:MM' o 'AAAA-MM-DD HH:MM', "
        "hora local); para 'todos los lunes a las 9' usá at='09:00', weekday='lunes', repeat='weekly'."
    )
    parameters = {
        "type": "object",
        "properties": {
            "message": {"type": "string", "description": "Qué recordar, ej. 'sacar la pizza del horno'."},
            "in_minutes": {"type": "number", "description": "Dentro de cuántos minutos (admite decimales)."},
            "at": {"type": "string", "description": "Hora local: 'HH:MM' o 'AAAA-MM-DD HH:MM'."},
            "weekday": {"type": "string", "description": "Día de la semana, ej. 'lunes'."},
            "repeat": {
                "type": "string",
                "enum": service.REPEATS,
                "description": "Repetición (por defecto none).",
            },
        },
        "required": ["message"],
    }
    risk_level = RiskLevel.LOW_RISK

    def execute(self, params: dict, context: ToolContext) -> ToolResult:
        try:
            in_minutes = params.get("in_minutes")
            due = service.resolve_due(
                datetime.now().astimezone(),
                in_seconds=float(in_minutes) * 60 if in_minutes is not None else None,
                at=params.get("at"),
                weekday=params.get("weekday"),
            )
            reminder = service.create_reminder(
                context.db, str(params.get("message", "")), due, params.get("repeat") or "none"
            )
        except (ValueError, TypeError) as exc:
            return ToolResult(success=False, error=str(exc))
        return ToolResult(success=True, data=f"Recordatorio creado (id={reminder.id}): {service.describe(reminder)}")


class ListRemindersTool(Tool):
    name = "list_reminders"
    description = "Lista los recordatorios y temporizadores pendientes, con su id."
    parameters = {"type": "object", "properties": {}, "required": []}
    risk_level = RiskLevel.READ_ONLY

    def execute(self, params: dict, context: ToolContext) -> ToolResult:
        pending = service.list_pending(context.db)
        if not pending:
            return ToolResult(success=True, data="No hay recordatorios pendientes.")
        return ToolResult(success=True, data="; ".join(f"id={r.id}: {service.describe(r)}" for r in pending))


class CancelReminderTool(Tool):
    name = "cancel_reminder"
    description = "Cancela un recordatorio pendiente por su id (ver list_reminders)."
    parameters = {
        "type": "object",
        "properties": {"reminder_id": {"type": "integer", "description": "Id del recordatorio."}},
        "required": ["reminder_id"],
    }
    risk_level = RiskLevel.LOW_RISK

    def execute(self, params: dict, context: ToolContext) -> ToolResult:
        try:
            reminder_id = int(params.get("reminder_id"))
        except (TypeError, ValueError):
            return ToolResult(success=False, error="El parámetro 'reminder_id' debe ser un número.")
        if not service.cancel_reminder(context.db, reminder_id):
            return ToolResult(success=False, error=f"No hay ningún recordatorio pendiente con id {reminder_id}.")
        return ToolResult(success=True, data=f"Recordatorio {reminder_id} cancelado.")
