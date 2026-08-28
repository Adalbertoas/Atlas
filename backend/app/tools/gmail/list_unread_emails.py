from __future__ import annotations

from app.integrations.gmail import GmailClient
from app.security.permissions import RiskLevel
from app.tools.base import Tool, ToolContext, ToolResult


class ListUnreadEmailsTool(Tool):
    name = "list_unread_emails"
    description = (
        "Lista los correos sin leer de Gmail: asunto, remitente y un fragmento del cuerpo. "
        "Usar para '¿tengo correos nuevos?', '¿qué mails sin leer tengo?'. No marca los correos "
        "como leídos ni los modifica."
    )
    parameters = {
        "type": "object",
        "properties": {
            "max_results": {
                "type": "integer",
                "description": "Cuántos traer como máximo (default 5).",
            },
        },
        "required": [],
    }
    risk_level = RiskLevel.READ_ONLY

    def __init__(self, client: GmailClient) -> None:
        self._client = client

    def execute(self, params: dict, context: ToolContext) -> ToolResult:
        max_results = params.get("max_results") or 5
        try:
            emails = self._client.list_unread(max_results=max_results)
        except Exception as exc:  # noqa: BLE001
            return ToolResult(success=False, error=str(exc))

        if not emails:
            return ToolResult(success=True, data="No hay correos sin leer.")

        summary = "; ".join(f"De {e.sender}: '{e.subject}' — {e.snippet}" for e in emails)
        return ToolResult(success=True, data=summary)
