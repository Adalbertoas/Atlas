from __future__ import annotations

from datetime import datetime

from app.security.permissions import RiskLevel
from app.tools.base import Tool, ToolContext, ToolResult


class GetCurrentTimeTool(Tool):
    name = "get_current_time"
    description = "Devuelve la fecha y hora actuales del sistema."
    parameters = {"type": "object", "properties": {}, "required": []}
    risk_level = RiskLevel.READ_ONLY

    def execute(self, params: dict, context: ToolContext) -> ToolResult:
        now = datetime.now()
        return ToolResult(success=True, data=now.strftime("%Y-%m-%d %H:%M:%S"))
