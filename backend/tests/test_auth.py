from __future__ import annotations

import pytest

from app.security.auth import create_access_token, get_current_user, verify_password


def test_verify_password_accepts_correct_password():
    assert verify_password("test-password") is True


def test_verify_password_rejects_wrong_password():
    assert verify_password("algo-incorrecto") is False


def test_create_and_decode_access_token():
    from fastapi.security import HTTPAuthorizationCredentials

    token = create_access_token()
    credentials = HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)
    assert get_current_user(credentials) == "local_user"


def test_get_current_user_rejects_missing_credentials():
    from fastapi import HTTPException

    with pytest.raises(HTTPException) as exc_info:
        get_current_user(None)
    assert exc_info.value.status_code == 401


def test_get_current_user_rejects_garbage_token():
    from fastapi import HTTPException
    from fastapi.security import HTTPAuthorizationCredentials

    credentials = HTTPAuthorizationCredentials(scheme="Bearer", credentials="esto-no-es-un-jwt")
    with pytest.raises(HTTPException) as exc_info:
        get_current_user(credentials)
    assert exc_info.value.status_code == 401


@pytest.fixture()
def auth_disabled(monkeypatch):
    from app.config import get_settings

    monkeypatch.setattr(get_settings(), "auth_enabled", False)


def test_auth_disabled_accepts_any_password(auth_disabled):
    assert verify_password("") is True
    assert verify_password("algo-incorrecto") is True


def test_auth_disabled_skips_token_checks(auth_disabled):
    from app.security.auth import is_token_valid

    assert get_current_user(None) == "local_user"
    assert is_token_valid("") is True


def test_auth_disabled_opens_protected_endpoints(client, auth_disabled):
    response = client.get("/api/v1/notifications")
    assert response.status_code != 401
