"""Autenticación de ATLAS (Fase 7, sección 17 del prompt maestro).

Sistema de un solo usuario (no multi-tenant): no hay tabla de usuarios, la
contraseña se compara contra ATLAS_PASSWORD (.env). El JWT resultante es lo
que separa "cualquiera en mi WiFi" de "yo autenticado" — necesario desde
que existe un cliente remoto (móvil) además del escritorio local.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.config import get_settings

_ALGORITHM = "HS256"
_SUBJECT = "local_user"  # único usuario del sistema

_bearer_scheme = HTTPBearer(auto_error=False)


def verify_password(password: str) -> bool:
    settings = get_settings()
    if not settings.atlas_password:
        # Sin contraseña configurada no hay forma segura de loguearse:
        # falla cerrado en vez de aceptar cualquier cosa.
        return False
    return password == settings.atlas_password


def create_access_token() -> str:
    settings = get_settings()
    expire = datetime.now(timezone.utc) + timedelta(minutes=settings.jwt_expire_minutes)
    payload = {"sub": _SUBJECT, "exp": expire}
    return jwt.encode(payload, settings.jwt_secret, algorithm=_ALGORITHM)


def _decode_token(token: str) -> dict:
    settings = get_settings()
    try:
        return jwt.decode(token, settings.jwt_secret, algorithms=[_ALGORITHM])
    except jwt.PyJWTError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token inválido o expirado.",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc


def is_token_valid(token: str) -> bool:
    """Para contextos que no son un request HTTP normal (ej. WebSocket, que
    no tiene el mismo mecanismo de excepciones) — no levanta HTTPException,
    solo dice si el token sirve."""
    try:
        jwt.decode(token, get_settings().jwt_secret, algorithms=[_ALGORITHM])
        return True
    except jwt.PyJWTError:
        return False


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer_scheme),
) -> str:
    """Dependencia de FastAPI: exige un Bearer token válido. Usar en cada
    endpoint que deba requerir login (todos salvo /system/health y /auth/login)."""
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Falta el token de autenticación.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    payload = _decode_token(credentials.credentials)
    return payload.get("sub", _SUBJECT)
