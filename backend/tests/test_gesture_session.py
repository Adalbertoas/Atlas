"""Tests del estado en vivo del control por gestos (Fase 13)."""
from __future__ import annotations

from app.gestures.session import GestureSessionTracker, gesture_session


def test_starts_disconnected():
    state = GestureSessionTracker().snapshot()
    assert state.connected is False
    assert state.connected_since is None
    assert state.events_received == 0


def test_connect_marks_active_and_stamps_time():
    tracker = GestureSessionTracker()
    tracker.connected()
    state = tracker.snapshot()
    assert state.connected is True
    assert state.connected_since is not None


def test_events_are_counted():
    tracker = GestureSessionTracker()
    tracker.connected()
    for _ in range(3):
        tracker.record_event()
    state = tracker.snapshot()
    assert state.events_received == 3
    assert state.last_event_at is not None


def test_disconnect_keeps_the_counter():
    """Al desconectar sigue interesando cuántos gestos hubo: el dashboard
    distingue "nunca se usó" de "la sesión terminó"."""
    tracker = GestureSessionTracker()
    tracker.connected()
    tracker.record_event()
    tracker.disconnected()

    state = tracker.snapshot()
    assert state.connected is False
    assert state.events_received == 1


def test_reconnecting_resets_the_counter():
    tracker = GestureSessionTracker()
    tracker.connected()
    tracker.record_event()
    tracker.connected()  # sesión nueva
    assert tracker.snapshot().events_received == 0


def test_snapshot_is_a_copy():
    """Mutar lo que devuelve snapshot() no debe tocar el estado compartido."""
    tracker = GestureSessionTracker()
    tracker.connected()
    snapshot = tracker.snapshot()
    snapshot.connected = False
    assert tracker.snapshot().connected is True


def test_status_endpoint_reports_state(client, auth_headers):
    gesture_session.disconnected()
    response = client.get("/api/v1/gestures/status", headers=auth_headers)
    assert response.status_code == 200
    assert response.json()["connected"] is False


def test_status_endpoint_requires_auth(client):
    """El router de gestos no está protegido a nivel de router (el WebSocket
    no puede usar HTTPBearer), así que este endpoint se protege solo."""
    assert client.get("/api/v1/gestures/status").status_code == 401


def test_profile_exposes_lan_ip(client, auth_headers):
    """El dashboard corre en 127.0.0.1 y necesita la IP de red para decirle
    al usuario qué abrir en el celular."""
    body = client.get("/api/v1/settings/profile", headers=auth_headers).json()
    assert "lan_ip" in body
    assert body["lan_ip"]
