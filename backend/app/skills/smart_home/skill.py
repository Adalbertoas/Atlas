from __future__ import annotations

from app.security.permissions import RiskLevel
from app.skills.base import Skill
from app.skills.models import SkillDefinition
from app.tools.base import ToolContext, ToolResult
from app.tools.registry import ToolRegistry


class SmartHomeSkill(Skill):
    definition = SkillDefinition(
        id="smart_home_overview", name="Estado del hogar", description="Consulta dispositivos del hogar inteligente.",
        required_tools=["list_devices"], instructions="Lista los dispositivos aplicando los filtros solicitados.",
        risk_level=RiskLevel.READ_ONLY, tags=["smart_home", "home", "devices"],
    )

    def execute(self, parameters: dict, context: ToolContext, tools: ToolRegistry) -> ToolResult:
        tool = tools.get("list_devices")
        if tool is None:
            return ToolResult(False, error="La herramienta requerida 'list_devices' no está disponible.")
        return tool.execute({k: v for k, v in parameters.items() if k in {"room", "type"}}, context)
