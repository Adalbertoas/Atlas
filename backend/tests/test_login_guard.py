"""Freno contra adivinar la contraseña de ATLAS (necesario al publicarlo en internet)."""
from __future__ import annotations

from app.security.login_guard import MAX_FAILURES, LoginGuard


def test_blocks_after_repeated_failures_and_expires():
    guard = LoginGuard(max_failures=3, window_seconds=60)
    for t in range(3):
        assert guard.retry_after("1.2.3.4", now=t) == 0
        guard.failed("1.2.3.4", now=t)
    assert guard.retry_after("1.2.3.4", now=10) > 0
    assert guard.retry_after("5.6.7.8", now=10) == 0  # otra dirección no se ve afectada
    assert guard.retry_after("1.2.3.4", now=200) == 0  # pasó la ventana


def test_success_clears_failures():
    guard = LoginGuard(max_failures=2, window_seconds=60)
    guard.failed("ip", now=0)
    guard.succeeded("ip")
    guard.failed("ip", now=1)
    assert guard.retry_after("ip", now=2) == 0


def test_login_endpoint_locks_out_by_cloudflare_client_ip(client):
    attacker = {"CF-Connecting-IP": "203.0.113.9"}
    for _ in range(MAX_FAILURES):
        assert client.post("/api/v1/auth/login", json={"password": "mal"}, headers=attacker).status_code == 401
    blocked = client.post("/api/v1/auth/login", json={"password": "test-password"}, headers=attacker)
    assert blocked.status_code == 429 and "Retry-After" in blocked.headers
    # El dueño, desde otra dirección, entra igual.
    ok = client.post("/api/v1/auth/login", json={"password": "test-password"}, headers={"CF-Connecting-IP": "198.51.100.1"})
    assert ok.status_code == 200
