"""Tests del rate limiting de /auth/login (sección 5, endurecido)."""
from __future__ import annotations

from app.security.rate_limit import LoginRateLimiter


# ---------- LoginRateLimiter (unidad) ----------


def test_allows_login_before_max_attempts():
    limiter = LoginRateLimiter(max_attempts=3, lockout_seconds=60)
    limiter.record_failure("1.2.3.4")
    limiter.record_failure("1.2.3.4")
    assert limiter.seconds_until_unlocked("1.2.3.4") == 0.0


def test_locks_after_max_attempts():
    limiter = LoginRateLimiter(max_attempts=3, lockout_seconds=60)
    for _ in range(3):
        limiter.record_failure("1.2.3.4")
    assert limiter.seconds_until_unlocked("1.2.3.4") > 0.0


def test_success_clears_failure_history():
    limiter = LoginRateLimiter(max_attempts=3, lockout_seconds=60)
    limiter.record_failure("1.2.3.4")
    limiter.record_failure("1.2.3.4")
    limiter.record_success("1.2.3.4")
    limiter.record_failure("1.2.3.4")
    # Solo 1 fallo desde el éxito: los dos previos no cuentan.
    assert limiter.seconds_until_unlocked("1.2.3.4") == 0.0


def test_ips_are_tracked_independently():
    limiter = LoginRateLimiter(max_attempts=2, lockout_seconds=60)
    limiter.record_failure("1.1.1.1")
    limiter.record_failure("1.1.1.1")
    assert limiter.seconds_until_unlocked("1.1.1.1") > 0.0
    assert limiter.seconds_until_unlocked("2.2.2.2") == 0.0


# ---------- Endpoint /auth/login ----------


def test_login_endpoint_locks_out_after_repeated_failures(client, monkeypatch):
    monkeypatch.setenv("LOGIN_MAX_ATTEMPTS", "3")
    from app.config import get_settings
    from app.security import rate_limit

    get_settings.cache_clear()
    monkeypatch.setattr(rate_limit, "login_rate_limiter", rate_limit.LoginRateLimiter())
    monkeypatch.setattr("app.api.v1.auth.login_rate_limiter", rate_limit.login_rate_limiter)

    for _ in range(3):
        response = client.post("/api/v1/auth/login", json={"password": "incorrecta"})
        assert response.status_code == 401

    response = client.post("/api/v1/auth/login", json={"password": "test-password"})  # correcta, no importa
    assert response.status_code == 429
    assert "Retry-After" in response.headers

    get_settings.cache_clear()


def test_login_endpoint_allows_correct_password_before_lockout(client):
    response = client.post("/api/v1/auth/login", json={"password": "incorrecta"})
    assert response.status_code == 401

    response = client.post("/api/v1/auth/login", json={"password": "test-password"})
    assert response.status_code == 200
    assert "access_token" in response.json()
