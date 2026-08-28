from __future__ import annotations

import pytest

from app.security.auth import create_access_token, get_current_user, revoke_token, verify_password


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


def test_revoked_token_is_rejected():
    from fastapi import HTTPException
    from fastapi.security import HTTPAuthorizationCredentials

    token = create_access_token()
    credentials = HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)
    assert get_current_user(credentials) == "local_user"  # válido antes de revocar

    revoke_token(token)

    with pytest.raises(HTTPException) as exc_info:
        get_current_user(credentials)
    assert exc_info.value.status_code == 401


def test_revoke_token_ignores_garbage_without_raising():
    revoke_token("esto-no-es-un-jwt")  # no debe levantar excepción


def test_revoking_one_token_does_not_affect_another():
    """Cada token tiene su propio jti — revocar uno no debe invalidar los demás
    (evita romper la sesión de otro dispositivo al cerrar sesión en uno)."""
    from fastapi.security import HTTPAuthorizationCredentials

    token_a = create_access_token()
    token_b = create_access_token()

    revoke_token(token_a)

    credentials_b = HTTPAuthorizationCredentials(scheme="Bearer", credentials=token_b)
    assert get_current_user(credentials_b) == "local_user"
