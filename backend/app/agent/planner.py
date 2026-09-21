"""Planificador determinista inicial.

Las decisiones de ejecución se expresan con IDs existentes, nunca se
interpretan instrucciones libres generadas por un modelo como código.
"""
from __future__ import annotations

from app.agent.models import AgentGoal, TaskPlan, TaskStep
from app.skills.registry import SkillRegistry
from app.tools.registry import ToolRegistry


class TaskPlanner:
    def __init__(self, skills: SkillRegistry, tools: ToolRegistry) -> None:
        self._skills = skills
        self._tools = tools

    def create_plan(self, goal_text: str) -> TaskPlan:
        goal = AgentGoal(description=goal_text.strip())
        text = goal.description.lower()
        steps: list[TaskStep] = []

        def add_skill(skill_id: str, description: str, parameters: dict | None = None) -> None:
            if self._skills.get(skill_id):
                steps.append(TaskStep(id=str(len(steps) + 1), description=description,
                                      target_type="skill", target_id=skill_id, parameters=parameters or {}))

        if any(word in text for word in ("computadora", "ordenador", "cpu", "ram", "recursos", "procesos", "sistema")):
            add_skill("system_overview", "Obtener métricas y procesos del sistema.")
        elif any(word in text for word in ("recuerda", "memoria", "guardado", "anoté", "anote")):
            add_skill("memory_lookup", "Buscar información en la memoria personal.", {"query": goal.description})
        elif any(word in text for word in ("casa", "hogar", "dispositivo", "luces", "smart home")):
            add_skill("smart_home_overview", "Consultar el estado de dispositivos del hogar.")
        elif any(word in text for word in ("hora", "fecha")) and self._tools.get("get_current_time"):
            steps.append(TaskStep(id="1", description="Consultar fecha y hora actual.", target_type="tool", target_id="get_current_time"))
        else:
            # Un paso explícitamente no ejecutable es más seguro que adivinar
            # una herramienta o convertir texto de usuario en una acción.
            steps.append(TaskStep(id="1", description="Analizar el objetivo sin ejecutar acciones.", target_type="analysis"))

        return TaskPlan(goal=goal, steps=steps)
