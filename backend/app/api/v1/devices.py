from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.deps import get_db_session
from app.smart_home import service
from app.smart_home.provider_factory import get_smart_home_provider
from app.smart_home.schemas import AssignRoomRequest, DeviceOut

router = APIRouter(prefix="/devices", tags=["devices"])


@router.get("", response_model=list[DeviceOut])
def list_devices(
    room: str | None = None,
    type: str | None = None,  # noqa: A002 — nombre de query param, no shadowing real
    db: Session = Depends(get_db_session),
) -> list[DeviceOut]:
    """Solo lectura, directo al SmartHomeProvider — no pasa por la IA (mismo
    criterio que GET /system/status)."""
    provider = get_smart_home_provider()
    devices = service.list_devices(db, provider, room=room, device_type=type)
    return [
        DeviceOut(id=d.id, name=d.name, room=d.room, type=d.type.value, state=d.state, capabilities=d.capabilities)
        for d in devices
    ]


@router.put("/{entity_id:path}/room")
def assign_room(entity_id: str, body: AssignRoomRequest, db: Session = Depends(get_db_session)) -> dict:
    provider = get_smart_home_provider()
    if provider.get_device(entity_id) is None:
        raise HTTPException(status_code=404, detail=f"Dispositivo '{entity_id}' no encontrado.")
    service.assign_device_room(db, entity_id, body.room_id)
    return {"assigned": True}
