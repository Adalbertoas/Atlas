from __future__ import annotations

from app.events.bus import EventBus, EventType
from app.security.permissions import RiskLevel
from app.smart_home.mock_provider import MockSmartHomeProvider
from app.smart_home.schemas import RoomCreate
from app.smart_home.service import assign_device_room, create_room, list_devices, list_rooms
from app.tools.base import ToolContext
from app.tools.smart_home.control_room import ControlRoomTool
from app.tools.smart_home.list_devices import ListDevicesTool
from app.tools.smart_home.set_device_state import SetDeviceStateTool


def test_create_and_list_rooms(db_session):
    create_room(db_session, RoomCreate(name="Oficina"))
    rooms = list_rooms(db_session)
    assert len(rooms) == 1
    assert rooms[0].name == "Oficina"


def test_list_devices_merges_room_assignment(db_session):
    provider = MockSmartHomeProvider()
    room = create_room(db_session, RoomCreate(name="Sala"))
    assign_device_room(db_session, "light.sala", room.id)

    devices = list_devices(db_session, provider)
    luz = next(d for d in devices if d.id == "light.sala")
    assert luz.room == "Sala"

    otros = [d for d in devices if d.id != "light.sala"]
    assert all(d.room is None for d in otros)


def test_list_devices_filters_by_room(db_session):
    provider = MockSmartHomeProvider()
    room = create_room(db_session, RoomCreate(name="Oficina"))
    assign_device_room(db_session, "switch.enchufe_oficina", room.id)

    devices = list_devices(db_session, provider, room="Oficina")
    assert len(devices) == 1
    assert devices[0].id == "switch.enchufe_oficina"


def test_list_devices_tool_returns_summary(db_session):
    tool = ListDevicesTool(MockSmartHomeProvider())
    result = tool.execute({}, ToolContext(db=db_session))
    assert result.success
    assert "Luz Sala" in result.data


def test_set_device_state_light_is_low_risk_and_turns_on(db_session):
    provider = MockSmartHomeProvider()
    tool = SetDeviceStateTool(provider, EventBus())

    assert tool.resolve_risk_level({"device": "Luz Sala"}) == RiskLevel.LOW_RISK

    result = tool.execute({"device": "Luz Sala", "action": "turn_on"}, ToolContext(db=db_session))
    assert result.success
    assert provider.get_device("light.sala").state == "on"


def test_set_device_state_publishes_device_state_changed(db_session):
    provider = MockSmartHomeProvider()
    events = EventBus()
    received = []
    events.subscribe(EventType.DEVICE_STATE_CHANGED, lambda e: received.append(e))
    tool = SetDeviceStateTool(provider, events)

    tool.execute({"device": "Luz Sala", "action": "turn_on"}, ToolContext(db=db_session))

    assert len(received) == 1
    assert received[0].payload == {"device_id": "light.sala", "state": "on"}


def test_set_device_state_lock_is_critical_risk(db_session):
    provider = MockSmartHomeProvider()
    tool = SetDeviceStateTool(provider, EventBus())
    assert tool.resolve_risk_level({"device": "Puerta Principal"}) == RiskLevel.CRITICAL


def test_set_device_state_unknown_device_defaults_to_medium_risk(db_session):
    tool = SetDeviceStateTool(MockSmartHomeProvider(), EventBus())
    assert tool.resolve_risk_level({"device": "algo-que-no-existe"}) == RiskLevel.MEDIUM_RISK


def test_control_room_only_affects_safe_types(db_session):
    provider = MockSmartHomeProvider()
    room = create_room(db_session, RoomCreate(name="Oficina"))
    assign_device_room(db_session, "switch.enchufe_oficina", room.id)
    assign_device_room(db_session, "lock.puerta_principal", room.id)  # nunca debe apagarse en bloque

    tool = ControlRoomTool(provider, EventBus())
    result = tool.execute({"room": "Oficina", "action": "turn_on"}, ToolContext(db=db_session))

    assert result.success
    assert "Enchufe Oficina" in result.data
    assert provider.get_device("switch.enchufe_oficina").state == "on"
    # La cerradura no se tocó pese a estar en la misma habitación.
    assert provider.get_device("lock.puerta_principal").state == "locked"
