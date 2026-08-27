"""Motor de base de datos de ATLAS.

V1 usa SQLite (ver app.config). El código de aquí en adelante (modelos,
servicios) no depende de SQLite específicamente: migrar a PostgreSQL en el
futuro solo requiere cambiar DATABASE_URL y el driver instalado.
"""
from __future__ import annotations

from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import get_settings

settings = get_settings()

_connect_args = {"check_same_thread": False} if settings.database_url.startswith("sqlite") else {}

engine = create_engine(settings.database_url, connect_args=_connect_args)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    pass


def init_db() -> None:
    """Crea las tablas si no existen. Para V1 no se usan migraciones formales
    (Alembic queda para cuando el esquema empiece a cambiar con frecuencia)."""
    # Importar los modelos para que se registren en Base.metadata antes de crear tablas.
    from app.automation import models as _automation_models  # noqa: F401
    from app.memory import models as _memory_models  # noqa: F401
    from app.notifications import models as _notifications_models  # noqa: F401
    from app.personality import models as _personality_models  # noqa: F401
    from app.reminders import models as _reminders_models  # noqa: F401
    from app.security import audit as _audit_models  # noqa: F401
    from app.smart_home import models as _smart_home_models  # noqa: F401

    Base.metadata.create_all(bind=engine)
    _add_missing_columns()


# Columnas agregadas después de que la base ya existía. `create_all` solo
# crea tablas nuevas: nunca toca una que ya está, así que un campo agregado
# a un modelo existente no aparece y todo revienta al consultarlo.
#
# V1 no usa Alembic a propósito (ver docstring de arriba), así que se
# resuelve con este parche mínimo en vez de pedirle al usuario que borre su
# base y pierda sus datos. Cuando el esquema cambie seguido, migrar a Alembic.
_LATE_COLUMNS: list[tuple[str, str, str]] = [
    # (tabla, columna, definición SQL)
    ("reminders", "notified", "BOOLEAN NOT NULL DEFAULT 0"),
]


def _add_missing_columns() -> None:
    from sqlalchemy import inspect, text

    inspector = inspect(engine)
    existing_tables = set(inspector.get_table_names())

    with engine.begin() as connection:
        for table, column, definition in _LATE_COLUMNS:
            if table not in existing_tables:
                continue  # create_all ya la creó completa
            columns = {c["name"] for c in inspector.get_columns(table)}
            if column in columns:
                continue
            connection.execute(text(f"ALTER TABLE {table} ADD COLUMN {column} {definition}"))


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
