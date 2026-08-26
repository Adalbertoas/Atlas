"""Servicio de Smart Home: junta el SmartHomeProvider (estado en vivo) con
las habitaciones propias de ATLAS (asignación local, sección 10)."""
from __future__ import annotations

from sqlalchemy.orm import Session

from app.smart_home.base import SmartDevice, SmartHomeProvider
from app.smart_home.models import Room, SmartDeviceMeta
from app.smart_home.schemas import RoomCreate, RoomOut


def list_rooms(db: Session) -> list[RoomOut]:
    return [RoomOut.model_validate(r) for r in db.query(Room).order_by(Room.name).all()]


def create_room(db: Session, data: RoomCreate) -> RoomOut:
    room = Room(name=data.name)
    db.add(room)
    db.commit()
    db.refresh(room)
    return RoomOut.model_validate(room)


def assign_device_room(db: Session, entity_id: str, room_id: int | None) -> None:
    meta = db.get(SmartDeviceMeta, entity_id)
    if meta is None:
        meta = SmartDeviceMeta(entity_id=entity_id, room_id=room_id)
        db.add(meta)
    else:
        meta.room_id = room_id
    db.commit()


def _room_names_by_entity(db: Session) -> dict[str, str]:
    rows = (
        db.query(SmartDeviceMeta.entity_id, Room.name)
        .join(Room, Room.id == SmartDeviceMeta.room_id)
        .all()
    )
    return dict(rows)


def list_devices(
    db: Session,
    provider: SmartHomeProvider,
    room: str | None = None,
    device_type: str | None = None,
) -> list[SmartDevice]:
    """Dispositivos con su habitación resuelta desde ATLAS (no del proveedor)."""
    room_by_entity = _room_names_by_entity(db)
    devices = provider.list_devices()
    for device in devices:
        device.room = room_by_entity.get(device.id)

    if room:
        devices = [d for d in devices if (d.room or "").lower() == room.lower()]
    if device_type:
        devices = [d for d in devices if d.type.value.lower() == device_type.lower()]
    return devices


def get_device_with_room(db: Session, provider: SmartHomeProvider, device_id: str) -> SmartDevice | None:
    device = provider.get_device(device_id)
    if device is None:
        return None
    meta = db.get(SmartDeviceMeta, device_id)
    if meta is not None and meta.room_id is not None:
        room = db.get(Room, meta.room_id)
        device.room = room.name if room else None
    return device
