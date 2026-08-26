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
    from app.security import audit as _audit_models  # noqa: F401
    from app.smart_home import models as _smart_home_models  # noqa: F401

    Base.metadata.create_all(bind=engine)


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
