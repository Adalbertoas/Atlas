"""Personalidad configurable de ATLAS (sección 8 del prompt maestro).

V1/Fase 2: un único perfil activo por proceso (una fila). Cuando exista
multi-usuario, esto se extiende con una FK a usuario sin cambiar la forma
de consumirlo (get_profile/build_system_prompt).
"""
from __future__ import annotations

from sqlalchemy import String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class PersonalityProfile(Base):
    __tablename__ = "personality_profiles"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    tone: Mapped[str] = mapped_column(String(200), default="profesional, tranquilo y ligeramente sofisticado")
    verbosity: Mapped[str] = mapped_column(String(20), default="breve")  # "breve" | "detallado"
    custom_instructions: Mapped[str] = mapped_column(Text, default="")
