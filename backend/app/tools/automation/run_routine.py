"""run_routine: dispara una rutina por nombre (sección 11).

LOW_RISK: execute_routine() ya filtra cualquier acción riesgosa antes de
tocarla (ver app/automation/service.py), así que el disparo en sí es
seguro — mismo criterio que control_room en Fase 5.
"""
from __future__ import annotations

from app.automation import service
from app.events.bus import EventBus
from app.security.permissions import RiskLevel
from app.tools.base import Tool, ToolContext, ToolResult
from app.tools.registry import ToolRegistry


class RunRoutineTool(Tool):
    name = "run_routine"
    description = "Ejecuta una rutina/automatización ya creada por su nombre, ej. 'Modo Dormir'."
    parameters = {
        "type": "object",
        "properties": {
            "routine_name": {"type": "string", "description": "Nombre de la rutina a ejecutar."}
        },
        "required": ["routine_name"],
    }
    risk_level = RiskLevel.LOW_RISK

    def __init__(self, registry: ToolRegistry, events: EventBus) -> None:
        self._registry = registry
        self._events = events

    def execute(self, params: dict, context: ToolContext) -> ToolResult:
        name = str(params.get("routine_name", "")).strip()
        if not name:
            return ToolResult(success=False, error="El parámetro 'routine_name' no puede estar vacío.")

        routine = service.get_routine_by_name(context.db, name)
        if routine is None:
            return ToolResult(success=False, error=f"No encontré ninguna rutina llamada '{name}'.")

        result = service.execute_routine(context.db, routine, self._registry, self._events)

        summary = f"Rutina '{result.routine_name}' ejecutada."
        if result.executed:
            summary += f" Hecho: {'; '.join(result.executed)}."
        if result.skipped:
            summary += f" Salteado (requiere confirmación manual): {'; '.join(result.skipped)}."
        return ToolResult(success=True, data=summary)
