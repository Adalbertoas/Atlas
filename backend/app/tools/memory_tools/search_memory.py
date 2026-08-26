from __future__ import annotations

from app.memory.service import list_memories, search_memories
from app.security.permissions import RiskLevel
from app.tools.base import Tool, ToolContext, ToolResult


class SearchMemoryTool(Tool):
    name = "search_memory"
    description = "Busca en la memoria personal de ATLAS. Si no se da 'query', lista lo más reciente."
    parameters = {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "Texto a buscar. Vacío = listar recientes."},
        },
        "required": [],
    }
    risk_level = RiskLevel.READ_ONLY

    def execute(self, params: dict, context: ToolContext) -> ToolResult:
        query = str(params.get("query") or "").strip()
        results = (
            search_memories(context.db, query) if query else list_memories(context.db, limit=10)
        )
        if not results:
            return ToolResult(success=True, data="No encontré nada guardado sobre eso.")

        summary = "; ".join(f"[{r.category}] {r.content}" for r in results)
        return ToolResult(success=True, data=summary)
