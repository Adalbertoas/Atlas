from __future__ import annotations

import time
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.agent.models import TaskPlan, TaskResult, TaskStatus
from app.config import get_settings
from app.events.bus import Event, EventBus, EventType
from app.security.audit import write_audit
from app.security.permissions import PermissionManager
from app.skills.registry import SkillRegistry
from app.tools.base import ToolContext
from app.tools.registry import ToolRegistry


class AgentExecutor:
    """Ejecuta un plan acotado, usando los servicios de seguridad existentes."""

    def __init__(self, tools: ToolRegistry, skills: SkillRegistry, permissions: PermissionManager, events: EventBus) -> None:
        self._tools, self._skills = tools, skills
        self._permissions, self._events = permissions, events

    def execute(self, db: Session, plan: TaskPlan) -> TaskResult:
        settings = get_settings()
        started = time.monotonic()
        plan.status = TaskStatus.RUNNING
        plan.goal.status = TaskStatus.RUNNING
        plan.started_at = plan.started_at or datetime.now(timezone.utc)

        while plan.current_step < len(plan.steps):
            if plan.current_step >= settings.agent_max_steps:
                return self._fail(plan, "Se alcanzó el límite configurado de pasos.")
            if plan.tool_calls >= settings.agent_max_tool_calls:
                return self._fail(plan, "Se alcanzó el límite configurado de llamadas a herramientas.")
            if time.monotonic() - started >= settings.agent_timeout_seconds:
                return self._fail(plan, "La tarea superó el tiempo máximo permitido.")

            step = plan.steps[plan.current_step]
            step.status = TaskStatus.RUNNING
            if step.target_type == "analysis":
                step.status = TaskStatus.COMPLETED
                step.result = "No hay una capacidad registrada para ejecutar este objetivo de forma segura."
                plan.current_step += 1
                continue

            target = self._skills.get(step.target_id or "") if step.target_type == "skill" else self._tools.get(step.target_id or "")
            if target is None:
                return self._fail(plan, f"No existe el destino '{step.target_id}' del paso {step.id}.")

            # Toda llamada de Tool, incluso la interna de una Skill, se revisa
            # antes. Las skills iniciales son solo de lectura; una Skill futura
            # con tools sensibles debe descomponerse en pasos explícitos.
            if step.target_type == "skill":
                missing = [name for name in target.required_tools() if self._tools.get(name) is None]
                if missing:
                    return self._fail(plan, f"La skill requiere herramientas no disponibles: {', '.join(missing)}.")
                sensitive = [name for name in target.required_tools() if self._tools.get(name).resolve_risk_level({}).value not in {"READ_ONLY", "LOW_RISK"}]
                if sensitive:
                    return self._fail(plan, "La skill contiene acciones sensibles y debe planificarse como pasos de tool separados.")
                result = target.execute(step.parameters, ToolContext(db=db), self._tools)
                plan.tool_calls += len(target.required_tools())
                risk_level = target.definition.risk_level.value
                audit_name = f"skill:{target.id}"
            else:
                risk = target.resolve_risk_level(step.parameters)
                decision = self._permissions.evaluate(
                    tool_name=target.name, risk_level=risk, parameters=step.parameters,
                    human_description=target.human_description(step.parameters), conversation_id=plan.id,
                )
                if decision.requires_confirmation:
                    step.status = TaskStatus.WAITING_CONFIRMATION
                    plan.status = plan.goal.status = TaskStatus.WAITING_CONFIRMATION
                    return self._result(plan, "La tarea espera tu confirmación.", decision.pending.id, decision.pending.description)
                result = target.execute(step.parameters, ToolContext(db=db))
                plan.tool_calls += 1
                risk_level, audit_name = risk.value, target.name

            step.result = result.data if result.success else None
            step.error = result.error
            step.status = TaskStatus.COMPLETED if result.success else TaskStatus.FAILED
            write_audit(db, tool_name=audit_name, parameters=step.parameters, risk_level=risk_level,
                        result_summary=result.as_text(), success=result.success)
            if not result.success:
                return self._fail(plan, result.error or f"Falló el paso {step.id}.")
            self._events.publish(Event(EventType.AGENT_STEP_COMPLETED, {"plan_id": plan.id, "step_id": step.id}))
            plan.current_step += 1

        plan.status = plan.goal.status = TaskStatus.COMPLETED
        plan.completed_at = datetime.now(timezone.utc)
        self._events.publish(Event(EventType.AGENT_TASK_COMPLETED, {"plan_id": plan.id}))
        return self._result(plan, "Objetivo completado.")

    def resume_confirmed(self, db: Session, plan: TaskPlan, confirmation_id: str) -> TaskResult:
        pending = self._permissions.resolve(confirmation_id)
        if pending is None or pending.conversation_id != plan.id:
            return self._fail(plan, "La confirmación ya no es válida para esta tarea.")
        step = plan.steps[plan.current_step]
        tool = self._tools.get(pending.tool_name)
        if tool is None:
            return self._fail(plan, f"La herramienta '{pending.tool_name}' ya no existe.")
        result = tool.execute(pending.parameters, ToolContext(db=db))
        plan.tool_calls += 1
        step.result, step.error = (result.data, None) if result.success else (None, result.error)
        step.status = TaskStatus.COMPLETED if result.success else TaskStatus.FAILED
        write_audit(db, tool_name=tool.name, parameters=pending.parameters, risk_level=pending.risk_level.value,
                    result_summary=result.as_text(), success=result.success)
        if not result.success:
            return self._fail(plan, result.error or "La acción confirmada falló.")
        plan.current_step += 1
        return self.execute(db, plan)

    def cancel_confirmation(self, confirmation_id: str) -> None:
        """Cancela usando el mismo PermissionManager que usa el chat."""
        self._permissions.resolve(confirmation_id)

    def _fail(self, plan: TaskPlan, reason: str) -> TaskResult:
        plan.status = plan.goal.status = TaskStatus.FAILED
        plan.failure_reason = reason
        plan.completed_at = datetime.now(timezone.utc)
        self._events.publish(Event(EventType.AGENT_TASK_FAILED, {"plan_id": plan.id, "reason": reason}))
        return self._result(plan, reason)

    @staticmethod
    def _result(plan: TaskPlan, summary: str, confirmation_id: str | None = None, confirmation_description: str | None = None) -> TaskResult:
        return TaskResult(plan_id=plan.id, status=plan.status, summary=summary, steps=plan.steps,
                          confirmation_id=confirmation_id, confirmation_description=confirmation_description)
