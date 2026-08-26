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
