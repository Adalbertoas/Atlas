from __future__ import annotations

from datetime import datetime

from app.reminders import service
from app.security.permissions import RiskLevel
from app.tools.base import Tool, ToolContext, ToolResult


class CreateReminderTool(Tool):
    name = "create_reminder"
    description = (
        "Crea un recordatorio con fecha y hora. Usar cuando el usuario pide que le "
        "recuerden algo ('recordame llamar al médico mañana a las 10'). La fecha/hora "
        "debe resolverse a un valor absoluto — si el usuario dice 'mañana', calcularlo "
        "usando get_current_time primero."
    )
    parameters = {
        "type": "object",
        "properties": {
            "text": {"type": "string", "description": "Qué recordar, ej. 'llamar al médico'."},
            "due_at": {
                "type": "string",
                "description": "Cuándo, en formato ISO 8601, ej. '2026-08-28T10:00:00'.",
            },
        },
        "required": ["text", "due_at"],
    }
    # LOW_RISK, no READ_ONLY: escribe en la base. No necesita confirmación
    # (crear un recordatorio no tiene consecuencias en el mundo real, a
    # diferencia de abrir una cerradura o cerrar una app).
    risk_level = RiskLevel.LOW_RISK

    def execute(self, params: dict, context: ToolContext) -> ToolResult:
        text = (params.get("text") or "").strip()
        if not text:
            return ToolResult(success=False, error="Falta el parámetro 'text'.")

        try:
            due_at = datetime.fromisoformat(params["due_at"])
        except (KeyError, ValueError) as exc:
            return ToolResult(
                success=False, error=f"'due_at' debe ser una fecha ISO 8601 válida: {exc}"
            )

        reminder = service.create_reminder(context.db, text=text, due_at=due_at)
        return ToolResult(
            success=True,
            data=f"Recordatorio creado: '{reminder.text}' para el {reminder.due_at:%d/%m/%Y a las %H:%M}.",
        )
