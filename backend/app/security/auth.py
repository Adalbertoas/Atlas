"""Autenticación de ATLAS (Fase 7, sección 17 del prompt maestro).

Sistema de un solo usuario (no multi-tenant): no hay tabla de usuarios, la
contraseña se compara contra ATLAS_PASSWORD (.env). El JWT resultante es lo
que separa "cualquiera en mi WiFi" de "yo autenticado" — necesario desde
que existe un cliente remoto (móvil) además del escritorio local.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.config import get_settings

_ALGORITHM = "HS256"
_SUBJECT = "local_user"  # único usuario del sistema

_bearer_scheme = HTTPBearer(auto_error=False)

# Tokens revocados (logout explícito) antes de que expiren solos. JWT es
# stateless por diseño — sin esto, un token robado seguía sirviendo hasta
# los JWT_EXPIRE_MINUTES (24h por defecto) aunque el dueño real cerrara
# sesión. Estado en memoria de proceso, mismo criterio que
# login_rate_limiter/permission_manager: para un solo usuario en un solo
# proceso alcanza. Se pierde en cada reinicio (incluido el --reload de
# uvicorn), que es aceptable: un reinicio ya invalida nada por sí mismo,
# esto solo cubre el caso de "cerrar sesión mientras el proceso sigue vivo".
_revoked_jtis: set[str] = set()


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
    payload = {"sub": _SUBJECT, "exp": expire, "jti": str(uuid.uuid4())}
    return jwt.encode(payload, settings.jwt_secret, algorithm=_ALGORITHM)


def _decode_token(token: str) -> dict:
    settings = get_settings()
    try:
        payload = jwt.decode(token, settings.jwt_secret, algorithms=[_ALGORITHM])
    except jwt.PyJWTError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token inválido o expirado.",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc
    if payload.get("jti") in _revoked_jtis:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Sesión cerrada. Iniciá sesión de nuevo.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return payload


def is_token_valid(token: str) -> bool:
    """Para contextos que no son un request HTTP normal (ej. WebSocket, que
    no tiene el mismo mecanismo de excepciones) — no levanta HTTPException,
    solo dice si el token sirve."""
    try:
        payload = jwt.decode(token, get_settings().jwt_secret, algorithms=[_ALGORITHM])
        return payload.get("jti") not in _revoked_jtis
    except jwt.PyJWTError:
        return False


def revoke_token(token: str) -> None:
    """Invalida un token antes de que expire solo (logout explícito).
    Un token ya inválido (firma mala, expirado) no tiene nada que revocar —
    se ignora en silencio, logout no debería poder fallar."""
    try:
        payload = jwt.decode(
            token, get_settings().jwt_secret, algorithms=[_ALGORITHM], options={"verify_exp": False}
        )
    except jwt.PyJWTError:
        return
    jti = payload.get("jti")
    if jti:
        _revoked_jtis.add(jti)


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


def get_current_token(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer_scheme),
) -> str:
    """Como get_current_user, pero devuelve el token crudo — lo necesita
    /auth/logout para saber qué jti revocar."""
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Falta el token de autenticación.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    _decode_token(credentials.credentials)  # valida antes de devolverlo
    return credentials.credentials
