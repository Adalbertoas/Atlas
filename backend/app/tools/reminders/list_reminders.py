from __future__ import annotations

from app.reminders import service
from app.security.permissions import RiskLevel
from app.tools.base import Tool, ToolContext, ToolResult


class ListRemindersTool(Tool):
    name = "list_reminders"
    description = "Lista los recordatorios del usuario, por defecto solo los pendientes."
    parameters = {
        "type": "object",
        "properties": {
            "include_done": {
                "type": "boolean",
                "description": "Si es true, incluye también los ya completados.",
            },
        },
        "required": [],
    }
    risk_level = RiskLevel.READ_ONLY

    def execute(self, params: dict, context: ToolContext) -> ToolResult:
        pending_only = not params.get("include_done", False)
        reminders = service.list_reminders(context.db, pending_only=pending_only)

        if not reminders:
            return ToolResult(success=True, data="No hay recordatorios pendientes.")

        summary = "; ".join(
            f"{r.text} ({r.due_at:%d/%m %H:%M}){' [hecho]' if r.done else ''}" for r in reminders
        )
        return ToolResult(success=True, data=summary)
