"""Tests de Web Push (Fase 22). Mockean pywebpush.webpush — no le pegan a
ningún servicio push real ni dependen de tener claves VAPID configuradas.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

from app.notifications.models import PushSubscription
from app.notifications.service import (
    remove_push_subscription,
    save_push_subscription,
    send_web_push,
)


# ---------- Suscripciones ----------


def test_save_push_subscription_creates_entry(db_session):
    save_push_subscription(db_session, endpoint="https://push.example/1", p256dh="key1", auth="auth1")
    entries = db_session.query(PushSubscription).all()
    assert len(entries) == 1
    assert entries[0].endpoint == "https://push.example/1"


def test_save_push_subscription_is_idempotent_by_endpoint(db_session):
    save_push_subscription(db_session, endpoint="https://push.example/1", p256dh="old", auth="old")
    save_push_subscription(db_session, endpoint="https://push.example/1", p256dh="new", auth="new")

    entries = db_session.query(PushSubscription).all()
    assert len(entries) == 1
    assert entries[0].p256dh == "new"


def test_remove_push_subscription(db_session):
    save_push_subscription(db_session, endpoint="https://push.example/1", p256dh="k", auth="a")
    assert remove_push_subscription(db_session, "https://push.example/1") is True
    assert db_session.query(PushSubscription).count() == 0


def test_remove_push_subscription_returns_false_for_unknown_endpoint(db_session):
    assert remove_push_subscription(db_session, "https://push.example/nope") is False


# ---------- Envío ----------


def test_send_web_push_does_nothing_without_vapid_keys(db_session, monkeypatch):
    monkeypatch.setenv("VAPID_PUBLIC_KEY", "")
    monkeypatch.setenv("VAPID_PRIVATE_KEY", "")
    from app.config import get_settings

    get_settings.cache_clear()
    save_push_subscription(db_session, endpoint="https://push.example/1", p256dh="k", auth="a")

    with patch("pywebpush.webpush") as webpush_mock:
        send_web_push(db_session, "hola")

    webpush_mock.assert_not_called()
    get_settings.cache_clear()


def test_send_web_push_calls_webpush_for_each_subscription(db_session, monkeypatch):
    monkeypatch.setenv("VAPID_PUBLIC_KEY", "pub")
    monkeypatch.setenv("VAPID_PRIVATE_KEY", "priv")
    monkeypatch.setenv("VAPID_CONTACT_EMAIL", "test@example.com")
    from app.config import get_settings

    get_settings.cache_clear()
    save_push_subscription(db_session, endpoint="https://push.example/1", p256dh="k1", auth="a1")
    save_push_subscription(db_session, endpoint="https://push.example/2", p256dh="k2", auth="a2")

    with patch("pywebpush.webpush") as webpush_mock:
        send_web_push(db_session, "Recordatorio: llamar al médico")

    assert webpush_mock.call_count == 2
    get_settings.cache_clear()


def test_send_web_push_removes_gone_subscription(db_session, monkeypatch):
    monkeypatch.setenv("VAPID_PUBLIC_KEY", "pub")
    monkeypatch.setenv("VAPID_PRIVATE_KEY", "priv")
    monkeypatch.setenv("VAPID_CONTACT_EMAIL", "test@example.com")
    from app.config import get_settings

    get_settings.cache_clear()
    save_push_subscription(db_session, endpoint="https://push.example/dead", p256dh="k", auth="a")

    from pywebpush import WebPushException

    fake_response = MagicMock(status_code=410)
    exc = WebPushException("gone")
    exc.response = fake_response

    with patch("pywebpush.webpush", side_effect=exc):
        send_web_push(db_session, "hola")

    assert db_session.query(PushSubscription).count() == 0
    get_settings.cache_clear()


def test_send_web_push_keeps_subscription_on_other_errors(db_session, monkeypatch):
    monkeypatch.setenv("VAPID_PUBLIC_KEY", "pub")
    monkeypatch.setenv("VAPID_PRIVATE_KEY", "priv")
    monkeypatch.setenv("VAPID_CONTACT_EMAIL", "test@example.com")
    from app.config import get_settings

    get_settings.cache_clear()
    save_push_subscription(db_session, endpoint="https://push.example/1", p256dh="k", auth="a")

    from pywebpush import WebPushException

    fake_response = MagicMock(status_code=500)
    exc = WebPushException("server error")
    exc.response = fake_response

    with patch("pywebpush.webpush", side_effect=exc):
        send_web_push(db_session, "hola")

    # Error transitorio del servicio push: no se borra la suscripción.
    assert db_session.query(PushSubscription).count() == 1
    get_settings.cache_clear()


# ---------- API ----------


def test_subscribe_and_unsubscribe_endpoints(client, auth_headers):
    response = client.post(
        "/api/v1/notifications/push/subscribe",
        json={"endpoint": "https://push.example/1", "keys": {"p256dh": "k", "auth": "a"}},
        headers=auth_headers,
    )
    assert response.status_code == 200
    assert response.json()["subscribed"] is True

    response = client.delete(
        "/api/v1/notifications/push/subscribe",
        params={"endpoint": "https://push.example/1"},
        headers=auth_headers,
    )
    assert response.status_code == 200
    assert response.json()["subscribed"] is False


def test_subscribe_requires_auth(client):
    response = client.post(
        "/api/v1/notifications/push/subscribe",
        json={"endpoint": "https://push.example/1", "keys": {"p256dh": "k", "auth": "a"}},
    )
    assert response.status_code == 401


def test_get_public_key_endpoint(client, auth_headers, monkeypatch):
    monkeypatch.setenv("VAPID_PUBLIC_KEY", "fake-public-key")
    from app.config import get_settings

    get_settings.cache_clear()

    response = client.get("/api/v1/notifications/push/public-key", headers=auth_headers)

    get_settings.cache_clear()
    assert response.status_code == 200
    assert response.json()["public_key"] == "fake-public-key"
