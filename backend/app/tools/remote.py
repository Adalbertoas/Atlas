"""Tools de la PC cuando el backend corre en un servidor: se ejecutan en el
agente de la PC (ver app/agent/hub.py). Mismo nombre, descripción, parámetros
y nivel de riesgo que la tool original: el modelo y el control de permisos no
notan la diferencia; solo cambia dónde corre."""
from __future__ import annotations

import concurrent.futures

from app.agent.hub import AgentHub, AgentOffline
from app.security.permissions import RiskLevel
from app.tools.base import Tool, ToolContext, ToolImage, ToolResult

PC_OFFLINE = (
    "Tu PC está apagada o el agente de ATLAS no está conectado, así que ahora no puedo hacer eso "
    "(abrir programas, ver la pantalla, archivos o el volumen dependen de la PC)."
)


class RemoteTool(Tool):
    def __init__(self, original: Tool, hub: AgentHub, timeout: float = 60) -> None:
        self._original = original
        self._hub = hub
        self._timeout = timeout
        self.name = original.name
        self.description = original.description
        self.parameters = original.parameters
        self.risk_level = original.risk_level

    def human_description(self, params: dict) -> str:
        return self._original.human_description(params)

    def resolve_risk_level(self, params: dict) -> RiskLevel:
        return self._original.resolve_risk_level(params)

    def execute(self, params: dict, context: ToolContext) -> ToolResult:
        try:
            result = self._hub.call(self.name, params, timeout=self._timeout)
        except AgentOffline:
            return ToolResult(success=False, error=PC_OFFLINE)
        except (TimeoutError, concurrent.futures.TimeoutError):
            return ToolResult(success=False, error="La PC no respondió a tiempo.")
        images = [ToolImage(mime_type=i.get("mime_type", "image/png"), data=i.get("data", "")) for i in result.get("images") or []]
        return ToolResult(success=bool(result.get("success")), data=result.get("data"), error=result.get("error"), images=images)
