from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from app.config import get_settings
from app.security.auth import create_access_token, get_current_token, revoke_token, verify_password
from app.security.rate_limit import login_rate_limiter

router = APIRouter(prefix="/auth", tags=["auth"])


class LoginRequest(BaseModel):
    password: str


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in_minutes: int


@router.post("/login", response_model=LoginResponse)
def login(body: LoginRequest, request: Request) -> LoginResponse:
    ip = request.client.host if request.client else "unknown"

    locked_seconds = login_rate_limiter.seconds_until_unlocked(ip)
    if locked_seconds > 0:
        raise HTTPException(
            status_code=429,
            detail=f"Demasiados intentos fallidos. Probá de nuevo en {round(locked_seconds / 60)} minutos.",
            headers={"Retry-After": str(round(locked_seconds))},
        )

    if not verify_password(body.password):
        login_rate_limiter.record_failure(ip)
        raise HTTPException(status_code=401, detail="Contraseña incorrecta.")

    login_rate_limiter.record_success(ip)
    token = create_access_token()
    return LoginResponse(access_token=token, expires_in_minutes=get_settings().jwt_expire_minutes)


@router.post("/logout")
def logout(token: str = Depends(get_current_token)) -> dict:
    """Revoca el token actual server-side. Sin esto, cerrar sesión solo
    borraba el token del cliente (localStorage) — uno filtrado o copiado
    antes seguía sirviendo hasta que expirara solo (JWT_EXPIRE_MINUTES,
    24h por defecto)."""
    revoke_token(token)
    return {"detail": "Sesión cerrada."}
