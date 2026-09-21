from __future__ import annotations

from app.security.permissions import RiskLevel
from app.skills.base import Skill
from app.skills.models import SkillDefinition
from app.tools.base import ToolContext, ToolResult
from app.tools.registry import ToolRegistry


class MemorySkill(Skill):
    definition = SkillDefinition(
        id="memory_lookup", name="Consulta de memoria", description="Busca información personal guardada.",
        required_tools=["search_memory"], instructions="Busca la consulta provista en la memoria.",
        risk_level=RiskLevel.READ_ONLY, tags=["memory", "personal"],
    )

    def execute(self, parameters: dict, context: ToolContext, tools: ToolRegistry) -> ToolResult:
        tool = tools.get("search_memory")
        if tool is None:
            return ToolResult(False, error="La herramienta requerida 'search_memory' no está disponible.")
        return tool.execute({"query": str(parameters.get("query", ""))}, context)
