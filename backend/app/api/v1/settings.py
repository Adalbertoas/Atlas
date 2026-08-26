from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_db_session
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
