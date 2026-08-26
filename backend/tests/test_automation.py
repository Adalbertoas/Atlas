from __future__ import annotations

from app.automation.schemas import ActionCreate, RoutineCreate, TriggerCreate
from app.automation.service import create_routine, delete_routine, execute_routine, list_routines
from app.events.bus import EventBus, EventType
from app.smart_home.mock_provider import MockSmartHomeProvider
from app.tools.automation.run_routine import RunRoutineTool
from app.tools.base import ToolContext
from app.tools.registry import ToolRegistry
from app.tools.smart_home.control_room import ControlRoomTool
from app.tools.smart_home.list_devices import ListDevicesTool
from app.tools.smart_home.set_device_state import SetDeviceStateTool
from app.tools.vision.analyze_screenshot import AnalyzeScreenshotTool
from app.vision.mock_provider import MockVisionProvider


def _registry_with_smart_home(provider, events) -> ToolRegistry:
    registry = ToolRegistry()
    registry.register(ListDevicesTool(provider))
    registry.register(SetDeviceStateTool(provider, events))
    registry.register(ControlRoomTool(provider, events))
    registry.register(AnalyzeScreenshotTool(MockVisionProvider()))
    registry.register(RunRoutineTool(registry, events))
    return registry


def test_create_and_list_routine(db_session):
    create_routine(
        db_session,
        RoutineCreate(
            name="Modo Dormir",
            actions=[ActionCreate(tool_name="set_device_state", params={"device": "Luz Sala", "action": "turn_off"})],
            triggers=[TriggerCreate(type="SCHEDULE", config={"time": "23:00"})],
        ),
    )
    routines = list_routines(db_session)
    assert len(routines) == 1
    assert routines[0].name == "Modo Dormir"
    assert routines[0].actions[0].tool_name == "set_device_state"
    assert routines[0].triggers[0].type == "SCHEDULE"


def test_execute_routine_runs_safe_actions(db_session):
    provider = MockSmartHomeProvider()
    events = EventBus()
    registry = _registry_with_smart_home(provider, events)

    routine = create_routine(
        db_session,
        RoutineCreate(
            name="Modo Dormir",
            actions=[ActionCreate(tool_name="set_device_state", params={"device": "Luz Sala", "action": "turn_off"})],
        ),
    )
    from app.automation.models import Routine

    routine_row = db_session.get(Routine, routine.id)
    result = execute_routine(db_session, routine_row, registry, events)

    assert result.executed
    assert not result.skipped
    assert provider.get_device("light.sala").state == "off"


def test_execute_routine_skips_actions_requiring_confirmation_and_notifies(db_session):
    provider = MockSmartHomeProvider()
    events = EventBus()
    registry = _registry_with_smart_home(provider, events)
    notifications = []
    events.subscribe(EventType.NOTIFICATION_CREATED, lambda e: notifications.append(e))

    routine = create_routine(
        db_session,
        RoutineCreate(
            name="Rutina riesgosa",
            actions=[
                ActionCreate(tool_name="set_device_state", params={"device": "Puerta Principal", "action": "unlock"})
            ],
        ),
    )
    from app.automation.models import Routine

    routine_row = db_session.get(Routine, routine.id)
    result = execute_routine(db_session, routine_row, registry, events)

    assert not result.executed
    assert result.skipped
    assert provider.get_device("lock.puerta_principal").state == "locked"  # nunca se tocó
    assert len(notifications) == 1


def test_execute_routine_publishes_lifecycle_events(db_session):
    provider = MockSmartHomeProvider()
    events = EventBus()
    registry = _registry_with_smart_home(provider, events)
    seen_types = []
    for event_type in (EventType.AUTOMATION_TRIGGERED, EventType.AUTOMATION_COMPLETED):
        events.subscribe(event_type, lambda e: seen_types.append(e.type))

    routine = create_routine(db_session, RoutineCreate(name="Vacía"))
    from app.automation.models import Routine

    routine_row = db_session.get(Routine, routine.id)
    execute_routine(db_session, routine_row, registry, events)

    assert EventType.AUTOMATION_TRIGGERED in seen_types
    assert EventType.AUTOMATION_COMPLETED in seen_types


def test_run_routine_tool_executes_by_name(db_session):
    provider = MockSmartHomeProvider()
    events = EventBus()
    registry = _registry_with_smart_home(provider, events)

    create_routine(
        db_session,
        RoutineCreate(
            name="Modo Dormir",
            actions=[ActionCreate(tool_name="set_device_state", params={"device": "Luz Sala", "action": "turn_off"})],
        ),
    )

    tool = registry.get("run_routine")
    result = tool.execute({"routine_name": "Modo Dormir"}, ToolContext(db=db_session))

    assert result.success
    assert provider.get_device("light.sala").state == "off"


def test_run_routine_tool_reports_unknown_routine(db_session):
    events = EventBus()
    registry = _registry_with_smart_home(MockSmartHomeProvider(), events)
    tool = registry.get("run_routine")

    result = tool.execute({"routine_name": "no existe"}, ToolContext(db=db_session))

    assert not result.success


def test_delete_routine(db_session):
    routine = create_routine(db_session, RoutineCreate(name="Temporal"))
    assert delete_routine(db_session, routine.id) is True
    assert delete_routine(db_session, routine.id) is False


def test_execute_routine_never_takes_a_screenshot_unattended(db_session):
    # HIGH_RISK (Fase 8) — igual regla que las acciones CRITICAL de Fase 6:
    # una rutina nunca la ejecuta sola, sin importar quién/qué la disparó.
    provider = MockSmartHomeProvider()
    events = EventBus()
    registry = _registry_with_smart_home(provider, events)

    routine = create_routine(
        db_session,
        RoutineCreate(name="Mirar pantalla", actions=[ActionCreate(tool_name="analyze_screenshot", params={})]),
    )
    from app.automation.models import Routine

    routine_row = db_session.get(Routine, routine.id)
    result = execute_routine(db_session, routine_row, registry, events)

    assert not result.executed
    assert result.skipped
