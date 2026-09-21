from __future__ import annotations

from app.security.permissions import RiskLevel
from app.skills.base import Skill
from app.skills.models import SkillDefinition
from app.tools.base import ToolContext, ToolResult
from app.tools.registry import ToolRegistry


class SystemSkill(Skill):
    definition = SkillDefinition(
        id="system_overview", name="Diagnóstico del sistema",
        description="Reúne métricas del equipo y los procesos de mayor consumo.",
        required_tools=["get_system_info", "list_processes"],
        instructions="Consulta las métricas y los procesos; resume solo los resultados obtenidos.",
        risk_level=RiskLevel.READ_ONLY, tags=["system", "computer", "performance"],
    )

    def execute(self, parameters: dict, context: ToolContext, tools: ToolRegistry) -> ToolResult:
        results = {}
        for name in self.required_tools():
            tool = tools.get(name)
            if tool is None:
                return ToolResult(False, error=f"La herramienta requerida '{name}' no está disponible.")
            result = tool.execute({}, context)
            if not result.success:
                return result
            results[name] = result.data
        return ToolResult(True, data=results)
