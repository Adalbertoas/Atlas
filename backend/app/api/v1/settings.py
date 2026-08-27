from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_db_session
from app.config import get_settings
from app.personality import service
from app.personality.schemas import PersonalityOut, PersonalityUpdate

router = APIRouter(prefix="/settings", tags=["settings"])


def _lan_ip() -> str:
    """IP de esta PC en la red local. El dashboard se abre en 127.0.0.1 y no
    tiene forma de saberla por su cuenta, pero la necesita para decirle al
    usuario qué URL abrir en el celular (PWA y control por gestos).

    Mismo truco que mobile/serve.py: abrir un socket UDP no envía nada, solo
    fuerza al SO a elegir la interfaz de salida."""
    import socket

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.connect(("8.8.8.8", 80))
        return sock.getsockname()[0]
    except OSError:
        return "127.0.0.1"
    finally:
        sock.close()


@router.get("/profile")
def get_profile() -> dict:
    """Datos del usuario para la UI (Fase 11): el nombre del saludo del
    dashboard (ATLAS_USER_NAME en .env — cadena vacía si no se configuró, y
    ahí el cliente saluda sin nombre) y la IP local, para armar los enlaces
    que hay que abrir desde el celular."""
    settings = get_settings()
    return {
        "user_name": settings.atlas_user_name,
        "wake_word": settings.atlas_wake_word,
        "lan_ip": _lan_ip(),
    }


@router.get("/personality", response_model=PersonalityOut)
def get_personality(db: Session = Depends(get_db_session)) -> PersonalityOut:
    return service.get_profile(db)


@router.put("/personality", response_model=PersonalityOut)
def update_personality(
    body: PersonalityUpdate, db: Session = Depends(get_db_session)
) -> PersonalityOut:
    return service.update_profile(db, body)
