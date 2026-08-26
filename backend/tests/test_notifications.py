from __future__ import annotations

from app.events.bus import Event, EventBus, EventType
from app.notifications.service import list_notifications, mark_read, register_notification_subscriber


def test_notification_created_event_gets_persisted(db_session, monkeypatch):
    # register_notification_subscriber abre su propia sesión (SessionLocal)
    # en vez de usar la del test — se apunta al mismo engine in-memory
    # compartido vía StaticPool (ver conftest.db_session) parcheando
    # SessionLocal para este test.
    import app.notifications.service as service_module
    from sqlalchemy.orm import sessionmaker

    TestingSessionLocal = sessionmaker(bind=db_session.get_bind())
    monkeypatch.setattr(service_module, "SessionLocal", TestingSessionLocal)

    events = EventBus()
    register_notification_subscriber(events)
    events.publish(
        Event(
            type=EventType.NOTIFICATION_CREATED,
            payload={"routine": "Modo Dormir", "reason": "requiere confirmación"},
        )
    )

    notifications = list_notifications(db_session)
    assert len(notifications) == 1
    assert "Modo Dormir" in notifications[0].message
    assert notifications[0].read is False


def test_mark_read(db_session):
    from app.notifications.models import Notification

    entry = Notification(message="Prueba")
    db_session.add(entry)
    db_session.commit()
    db_session.refresh(entry)

    assert mark_read(db_session, entry.id) is True
    notifications = list_notifications(db_session, unread_only=True)
    assert notifications == []


def test_mark_read_returns_false_for_unknown_id(db_session):
    assert mark_read(db_session, 9999) is False
