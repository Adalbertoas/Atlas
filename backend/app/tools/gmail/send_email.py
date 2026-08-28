from __future__ import annotations

from app.integrations.gmail import GmailClient
from app.security.permissions import RiskLevel
from app.tools.base import Tool, ToolContext, ToolResult


class SendEmailTool(Tool):
    name = "send_email"
    description = (
        "Manda un correo desde la cuenta de Gmail del usuario. Usar cuando pide explícitamente "
        "mandar/escribir un mail a alguien. Requiere la dirección de destino exacta — si el "
        "usuario solo da un nombre ('mandale un mail a Juan'), preguntar la dirección antes de "
        "llamar a esta tool en vez de inventarla."
    )
    parameters = {
        "type": "object",
        "properties": {
            "to": {"type": "string", "description": "Dirección de destino."},
            "subject": {"type": "string", "description": "Asunto del correo."},
            "body": {"type": "string", "description": "Cuerpo del correo, texto plano."},
        },
        "required": ["to", "subject", "body"],
    }
    # MEDIUM_RISK, no LOW_RISK: a diferencia de crear un recordatorio o un
    # evento de calendario (que solo quedan en herramientas propias del
    # usuario), mandar un correo es una acción hacia afuera e irreversible
    # — llega a un tercero, no se puede "deshacer" borrándolo después.
    # Mismo nivel que close_application (sección 12).
    risk_level = RiskLevel.MEDIUM_RISK

    def __init__(self, client: GmailClient) -> None:
        self._client = client

    def human_description(self, params: dict) -> str:
        to = params.get("to", "?")
        subject = params.get("subject", "(sin asunto)")
        return f"Mandar un correo a {to} con asunto '{subject}'"

    def execute(self, params: dict, context: ToolContext) -> ToolResult:
        to = (params.get("to") or "").strip()
        subject = (params.get("subject") or "").strip()
        body = params.get("body") or ""
        if not to or not subject:
            return ToolResult(success=False, error="Faltan 'to' y/o 'subject'.")

        try:
            message_id = self._client.send(to=to, subject=subject, body=body)
        except Exception as exc:  # noqa: BLE001
            return ToolResult(success=False, error=str(exc))

        return ToolResult(success=True, data=f"Correo enviado a {to} (id={message_id}).")
