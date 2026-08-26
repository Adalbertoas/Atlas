from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.config import get_settings
from app.security.auth import create_access_token, verify_password

router = APIRouter(prefix="/auth", tags=["auth"])


class LoginRequest(BaseModel):
    password: str


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in_minutes: int


@router.post("/login", response_model=LoginResponse)
def login(body: LoginRequest) -> LoginResponse:
    if not verify_password(body.password):
        raise HTTPException(status_code=401, detail="Contraseña incorrecta.")

    token = create_access_token()
    return LoginResponse(access_token=token, expires_in_minutes=get_settings().jwt_expire_minutes)
