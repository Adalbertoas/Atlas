from __future__ import annotations

from app.agent.executor import AgentExecutor
from app.agent.models import AgentGoal, TaskPlan, TaskStatus, TaskStep
from app.agent.planner import TaskPlanner
from app.events.bus import EventBus
from app.security.permissions import PermissionManager, RiskLevel
from app.skills.registry import SkillRegistry
from app.tools.base import Tool, ToolContext, ToolResult
from app.tools.registry import ToolRegistry


class _SafeTool(Tool):
    name = "safe"
    description = "safe"
    parameters = {"type": "object", "properties": {}}
    risk_level = RiskLevel.READ_ONLY

    def execute(self, params: dict, context: ToolContext) -> ToolResult:
        return ToolResult(True, data="ok")


class _SensitiveTool(_SafeTool):
    name = "sensitive"
    risk_level = RiskLevel.MEDIUM_RISK


def _executor(registry: ToolRegistry) -> AgentExecutor:
    return AgentExecutor(registry, SkillRegistry(), PermissionManager(), EventBus())


def test_planner_uses_registered_system_skill():
    tools, skills = ToolRegistry(), SkillRegistry()
    from app.skills.system import SystemSkill

    skills.register(SystemSkill())
    plan = TaskPlanner(skills, tools).create_plan("Revisa recursos de mi computadora")
    assert plan.steps[0].target_type == "skill"
    assert plan.steps[0].target_id == "system_overview"


def test_executor_executes_structured_tool_and_audits(db_session):
    registry = ToolRegistry()
    registry.register(_SafeTool())
    plan = TaskPlan(goal=AgentGoal(description="probar"), steps=[
        TaskStep(id="1", description="ejecutar", target_type="tool", target_id="safe")
    ])
    result = _executor(registry).execute(db_session, plan)
    assert result.status == TaskStatus.COMPLETED
    assert result.steps[0].result == "ok"


def test_executor_waits_for_existing_permission_manager(db_session):
    registry = ToolRegistry()
    registry.register(_SensitiveTool())
    plan = TaskPlan(goal=AgentGoal(description="probar"), steps=[
        TaskStep(id="1", description="ejecutar", target_type="tool", target_id="sensitive")
    ])
    result = _executor(registry).execute(db_session, plan)
    assert result.status == TaskStatus.WAITING_CONFIRMATION
    assert result.confirmation_id


def test_agent_task_endpoint_builds_and_completes_system_plan(client, auth_headers):
    response = client.post(
        "/api/v1/agent/tasks",
        headers=auth_headers,
        json={"goal": "Revisa el estado de mi computadora y dime si algo consume demasiados recursos."},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "COMPLETED"
    assert payload["steps"][0]["target_id"] == "system_overview"
    assert "get_system_info" in payload["steps"][0]["result"]
