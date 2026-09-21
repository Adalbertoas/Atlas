from __future__ import annotations

from app.agent.executor import AgentExecutor
from app.agent.models import TaskPlan, TaskResult, TaskStatus
from app.agent.planner import TaskPlanner
from app.events.bus import Event, EventBus, EventType


class AgentService:
    """Fachada con estado de tareas en proceso.

    ATLAS actualmente usa confirmaciones en memoria de proceso; los planes se
    conservan con el mismo alcance para poder reanudar una tarea confirmada.
    """

    def __init__(self, planner: TaskPlanner, executor: AgentExecutor, events: EventBus) -> None:
        self._planner, self._executor, self._events = planner, executor, events
        self._plans: dict[str, TaskPlan] = {}
        self._confirmation_to_plan: dict[str, str] = {}

    def start(self, db, goal: str) -> TaskResult:
        plan = self._planner.create_plan(goal)
        self._plans[plan.id] = plan
        self._events.publish(Event(EventType.AGENT_TASK_STARTED, {"plan_id": plan.id, "goal": goal}))
        result = self._executor.execute(db, plan)
        self._track_confirmation(plan, result)
        return result

    def get_plan(self, plan_id: str) -> TaskPlan | None:
        return self._plans.get(plan_id)

    def confirm(self, db, plan_id: str, confirmation_id: str, approve: bool) -> TaskResult | None:
        plan = self._plans.get(plan_id)
        if plan is None or self._confirmation_to_plan.get(confirmation_id) != plan_id:
            return None
        self._confirmation_to_plan.pop(confirmation_id, None)
        if not approve:
            self._executor.cancel_confirmation(confirmation_id)
            plan.status = plan.goal.status = TaskStatus.CANCELLED
            return TaskResult(plan_id=plan.id, status=plan.status, summary="Tarea cancelada.", steps=plan.steps)
        result = self._executor.resume_confirmed(db, plan, confirmation_id)
        self._track_confirmation(plan, result)
        return result

    def _track_confirmation(self, plan: TaskPlan, result: TaskResult) -> None:
        if result.confirmation_id:
            self._confirmation_to_plan[result.confirmation_id] = plan.id
