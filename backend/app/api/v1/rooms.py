from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_db_session
from app.smart_home import service
from app.smart_home.schemas import RoomCreate, RoomOut

router = APIRouter(prefix="/rooms", tags=["rooms"])


@router.get("", response_model=list[RoomOut])
def list_rooms(db: Session = Depends(get_db_session)) -> list[RoomOut]:
    return service.list_rooms(db)


@router.post("", response_model=RoomOut)
def create_room(body: RoomCreate, db: Session = Depends(get_db_session)) -> RoomOut:
    return service.create_room(db, body)
