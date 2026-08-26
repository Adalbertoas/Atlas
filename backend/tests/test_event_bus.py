from __future__ import annotations

from app.events.bus import Event, EventBus, EventType


def test_subscriber_receives_published_event():
    bus = EventBus()
    received = []
    bus.subscribe(EventType.USER_COMMAND, lambda e: received.append(e))

    bus.publish(Event(type=EventType.USER_COMMAND, payload={"message": "hola"}))

    assert len(received) == 1
    assert received[0].payload["message"] == "hola"


def test_subscriber_only_receives_its_event_type():
    bus = EventBus()
    received = []
    bus.subscribe(EventType.SYSTEM_ALERT, lambda e: received.append(e))

    bus.publish(Event(type=EventType.USER_COMMAND, payload={}))

    assert received == []


def test_broken_subscriber_does_not_crash_publish():
    bus = EventBus()

    def broken_handler(event: Event) -> None:
        raise RuntimeError("boom")

    calls = []
    bus.subscribe(EventType.USER_COMMAND, broken_handler)
    bus.subscribe(EventType.USER_COMMAND, lambda e: calls.append(e))

    # No debe lanzar excepción aunque el primer subscriber falle.
    bus.publish(Event(type=EventType.USER_COMMAND, payload={}))

    assert len(calls) == 1
