"""Contrato de una Skill.

Una Skill compone herramientas registradas; nunca elude sus permisos ni
reimplementa la lógica que ya pertenece a una Tool.
"""
from __future__ import annotations

from abc import ABC, abstractmethod

from app.skills.models import SkillDefinition
from app.tools.base import ToolContext, ToolResult
from app.tools.registry import ToolRegistry


class Skill(ABC):
    definition: SkillDefinition

    @property
    def id(self) -> str:
        return self.definition.id

    def required_tools(self) -> list[str]:
        return self.definition.required_tools

    @abstractmethod
    def execute(self, parameters: dict, context: ToolContext, tools: ToolRegistry) -> ToolResult:
        """Ejecuta la composición ya autorizada por AgentExecutor."""
        raise NotImplementedError
