from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from app.config import get_settings
from app.security.auth import create_access_token, verify_password
from app.security.login_guard import client_key, login_guard

router = APIRouter(prefix="/auth", tags=["auth"])


class LoginRequest(BaseModel):
    password: str


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in_minutes: int


@router.post("/login", response_model=LoginResponse)
def login(body: LoginRequest, request: Request) -> LoginResponse:
    key = client_key(request)
    wait = login_guard.retry_after(key)
    if wait:
        raise HTTPException(
            status_code=429,
            detail=f"Demasiados intentos fallidos. Prueba de nuevo en {max(1, wait // 60)} minutos.",
            headers={"Retry-After": str(wait)},
        )
    if not verify_password(body.password):
        login_guard.failed(key)
        raise HTTPException(status_code=401, detail="Contraseña incorrecta.")
    login_guard.succeeded(key)

    token = create_access_token()
    return LoginResponse(access_token=token, expires_in_minutes=get_settings().jwt_expire_minutes)
