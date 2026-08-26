from __future__ import annotations

from app.memory.schemas import MemoryCreate
from app.memory.service import create_memory
from app.security.permissions import RiskLevel
from app.tools.base import Tool, ToolContext, ToolResult


class CreateMemoryTool(Tool):
    name = "create_memory"
    description = (
        "Guarda un dato en la memoria personal de ATLAS (preferencias, proyectos, "
        "información que el usuario pidió recordar)."
    )
    parameters = {
        "type": "object",
        "properties": {
            "content": {"type": "string", "description": "Lo que se debe recordar."},
            "category": {
                "type": "string",
                "description": "personal | preference | project | conversation_summary",
            },
            "tags": {"type": "array", "items": {"type": "string"}},
        },
        "required": ["content"],
    }
    risk_level = RiskLevel.LOW_RISK

    def execute(self, params: dict, context: ToolContext) -> ToolResult:
        content = str(params.get("content", "")).strip()
        if not content:
            return ToolResult(success=False, error="El parámetro 'content' no puede estar vacío.")

        data = MemoryCreate(
            content=content,
            category=params.get("category") or "personal",
            tags=list(params.get("tags") or []),
        )
        entry = create_memory(context.db, data)
        return ToolResult(success=True, data=f"Memoria guardada (id={entry.id}): {entry.content}")
