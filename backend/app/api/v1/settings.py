from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.deps import get_db_session
from app.core import keys
from app.personality import service
from app.personality.schemas import PersonalityOut, PersonalityUpdate

router = APIRouter(prefix="/settings", tags=["settings"])


@router.get("/personality", response_model=PersonalityOut)
def get_personality(db: Session = Depends(get_db_session)) -> PersonalityOut:
    return service.get_profile(db)


@router.put("/personality", response_model=PersonalityOut)
def update_personality(
    body: PersonalityUpdate, db: Session = Depends(get_db_session)
) -> PersonalityOut:
    return service.update_profile(db, body)


class KeysUpdate(BaseModel):
    # None = no tocar; "" = quitar la clave.
    openai_api_key: str | None = Field(default=None, max_length=500)
    image_default_engine: str | None = None


@router.get("/keys")
def get_keys() -> dict:
    """Estado de las claves: nunca devuelve la clave, solo si está y sus últimos 4 caracteres."""
    return keys.status()


@router.put("/keys")
async def update_keys(body: KeysUpdate) -> dict:
    try:
        return await run_in_threadpool(keys.update, body.openai_api_key, body.image_default_engine)
    except keys.KeySettingError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except OSError as exc:
        raise HTTPException(status_code=500, detail=f"No pude guardar en {keys.ENV_PATH} ({exc.strerror or exc}).") from exc
