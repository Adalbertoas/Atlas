"""Modelos de Smart Home propios de ATLAS (sección 10 del prompt maestro).

Room y SmartDeviceMeta son locales a ATLAS — no se importan del registro de
áreas de Home Assistant (ver docs/architecture.md, Fase 5). El estado real
de cada dispositivo (encendido, temperatura, etc.) nunca se guarda acá: se
consulta en vivo al SmartHomeProvider.
"""
from __future__ import annotations

from sqlalchemy import ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class Room(Base):
    __tablename__ = "rooms"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(100), unique=True)


class SmartDeviceMeta(Base):
    """Asignación de un dispositivo (identificado por su entity_id del
    proveedor) a una habitación de ATLAS."""

    __tablename__ = "smart_device_meta"

    entity_id: Mapped[str] = mapped_column(String(200), primary_key=True)
    room_id: Mapped[int | None] = mapped_column(ForeignKey("rooms.id"), nullable=True)
