"""Automation Engine: rutinas y triggers (sección 11 del prompt maestro)."""
from __future__ import annotations

from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class Routine(Base):
    __tablename__ = "routines"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(100), unique=True)


class RoutineAction(Base):
    """Un paso de la rutina: reutiliza una tool ya registrada
    (app/tools/registry.py), no reinventa ejecución."""

    __tablename__ = "routine_actions"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    routine_id: Mapped[int] = mapped_column(ForeignKey("routines.id"))
    tool_name: Mapped[str] = mapped_column(String(100))
    params_json: Mapped[str] = mapped_column(Text, default="{}")
    order: Mapped[int] = mapped_column(default=0)


class RoutineTrigger(Base):
    """SCHEDULE: config_json = {"time": "23:00"}.
    DEVICE_STATE: config_json = {"device_id": "...", "state": "..."}."""

    __tablename__ = "routine_triggers"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    routine_id: Mapped[int] = mapped_column(ForeignKey("routines.id"))
    type: Mapped[str] = mapped_column(String(20))  # "SCHEDULE" | "DEVICE_STATE"
    config_json: Mapped[str] = mapped_column(Text, default="{}")
