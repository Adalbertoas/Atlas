"""Personalidad configurable de ATLAS (sección 8 del prompt maestro).

V1/Fase 2: un único perfil activo por proceso (una fila). Cuando exista
multi-usuario, esto se extiende con una FK a usuario sin cambiar la forma
de consumirlo (get_profile/build_system_prompt).

Columnas agregadas después de la V1 (assistant_name en adelante): las bases
existentes las reciben con su valor por defecto al arrancar (ver
app.core.database.add_missing_columns).
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
    assistant_name: Mapped[str] = mapped_column(String(40), default="ATLAS", server_default="ATLAS")
    # Cómo llamar al usuario; vacío = sin nombre.
    user_name: Mapped[str] = mapped_column(String(80), default="", server_default="")
    formality: Mapped[str] = mapped_column(String(10), default="tu", server_default="tu")  # "tu" | "usted" | "vos"
    humor: Mapped[str] = mapped_column(String(20), default="sutil", server_default="sutil")  # "ninguno" | "sutil" | "frecuente"
    # Ciudad por defecto para clima y noticias locales.
    home_city: Mapped[str] = mapped_column(String(120), default="", server_default="")
