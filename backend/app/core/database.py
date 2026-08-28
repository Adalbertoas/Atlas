"""Motor de base de datos de ATLAS.

V1 usa SQLite (ver app.config). El código de aquí en adelante (modelos,
servicios) no depende de SQLite específicamente: migrar a PostgreSQL en el
futuro solo requiere cambiar DATABASE_URL y el driver instalado.
"""
from __future__ import annotations

from collections.abc import Generator
from pathlib import Path

from sqlalchemy import create_engine, inspect
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import get_settings

settings = get_settings()

_connect_args = {"check_same_thread": False} if settings.database_url.startswith("sqlite") else {}

engine = create_engine(settings.database_url, connect_args=_connect_args)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    pass


# backend/alembic.ini — dos niveles arriba de este archivo (app/core/database.py).
_ALEMBIC_INI = Path(__file__).resolve().parents[2] / "alembic.ini"

# Cualquier tabla de ATLAS sirve como "marca" de que la base ya existía antes
# de que este proyecto usara Alembic — no importa cuál, solo que sea de las
# que ya creaba create_all() en cualquier versión anterior.
_PRE_ALEMBIC_MARKER_TABLE = "conversation_messages"


def init_db() -> None:
    """Deja la base al día con `alembic upgrade head`.

    Hasta acá (V1-V28) esto era `Base.metadata.create_all()` + un parche a
    mano (`_add_missing_columns`) para las pocas columnas agregadas después
    de que la base ya existía — alcanzaba mientras el esquema casi no
    cambiaba, pero ya lleva dos parches de ese tipo (`reminders.notified`,
    `memory_entries.embedding`) y cada uno es una forma más de romper una
    base existente si alguien se olvida de escribirlo. Alembic reemplaza
    ambas cosas: crear la base desde cero *y* evolucionar una que ya existe
    son la misma operación (`upgrade head`), sin mantenimiento manual.

    El único caso que Alembic no resuelve solo es adoptar una base que ya
    existía *antes* de este cambio (el atlas.db de cualquiera que ya estaba
    usando ATLAS): esa base ya tiene todas las tablas de la migración
    baseline, así que "aplicarla" fallaría con "la tabla ya existe". Se
    detecta ese caso (tiene tablas de ATLAS pero no la tabla de control
    `alembic_version`, porque nunca corrió Alembic) y en vez de aplicar la
    baseline se la marca como ya aplicada (`stamp head`) — no toca el
    esquema, que ya está bien, solo el registro de qué migración le
    corresponde de acá en adelante.
    """
    from alembic import command
    from alembic.config import Config

    cfg = Config(str(_ALEMBIC_INI))
    cfg.set_main_option("script_location", str(_ALEMBIC_INI.parent / "migrations"))
    cfg.set_main_option("sqlalchemy.url", settings.database_url)
    # El Engine real de la app, no uno nuevo armado a partir de la URL: con
    # SQLite ":memory:" (el caso de los tests) una conexión nueva es una
    # base vacía y distinta de la que el resto de ATLAS va a usar — ver
    # migrations/env.py para el detalle completo del bug que esto evita.
    cfg.attributes["connection"] = engine

    inspector = inspect(engine)
    existing_tables = set(inspector.get_table_names())
    is_pre_alembic_db = (
        _PRE_ALEMBIC_MARKER_TABLE in existing_tables and "alembic_version" not in existing_tables
    )

    if is_pre_alembic_db:
        command.stamp(cfg, "head")
    else:
        command.upgrade(cfg, "head")


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
