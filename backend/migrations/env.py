"""Entorno de Alembic para ATLAS.

Dos cosas no vienen del template estándar de `alembic init`:

1. `target_metadata` sale de `app.core.database.Base`, con todos los modelos
   importados primero (si no, `Base.metadata` está vacío y autogenerate no
   detecta ninguna tabla) — mismo listado que usaba `init_db()` antes de
   este cambio.
2. La URL de conexión sale de `app.config.get_settings().database_url`, no
   de `alembic.ini` — ATLAS ya tiene un único lugar para eso (`.env`), y
   duplicarlo en alembic.ini es la forma más fácil de que se desincronicen
   (ej. correr migraciones contra la base equivocada sin darse cuenta).
"""
from logging.config import fileConfig

from sqlalchemy import engine_from_config, pool

from alembic import context

# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config

# Interpret the config file for Python logging.
# This line sets up loggers basically.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Importar los modelos para que se registren en Base.metadata antes de que
# Alembic la use — mismo listado (y misma razón) que app.core.database.init_db().
from app.automation import models as _automation_models  # noqa: E402,F401
from app.core import usage as _usage_models  # noqa: E402,F401
from app.core.database import Base  # noqa: E402
from app.memory import models as _memory_models  # noqa: E402,F401
from app.notifications import models as _notifications_models  # noqa: E402,F401
from app.personality import models as _personality_models  # noqa: E402,F401
from app.reminders import models as _reminders_models  # noqa: E402,F401
from app.security import audit as _audit_models  # noqa: E402,F401
from app.smart_home import models as _smart_home_models  # noqa: E402,F401

target_metadata = Base.metadata

# Sobreescribe el placeholder de alembic.ini con la URL real de ATLAS.
from app.config import get_settings  # noqa: E402

config.set_main_option("sqlalchemy.url", get_settings().database_url)


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode.

    This configures the context with just a URL
    and not an Engine, though an Engine is acceptable
    here as well.  By skipping the Engine creation
    we don't even need a DBAPI to be available.

    Calls to context.execute() here emit the given string to the
    script output.

    """
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode.

    In this scenario we need to create an Engine
    and associate a connection with the context.

    ATLAS: si quien llama (app.core.database.init_db) ya pasó su propio
    Engine vía `config.attributes["connection"]`, se reusa ese en vez de
    crear uno nuevo con NullPool. Crítico para SQLite ":memory:" — una base
    en memoria vive únicamente en la conexión que la creó, así que un Engine
    nuevo (aunque apunte a la misma URL) es una base vacía y distinta;
    aplicar la migración ahí no le sirve de nada al Engine real de la app,
    que se queda sin las tablas (bug real, encontrado al probar esto en
    vivo). Con una URL de archivo (el caso normal, `sqlite:///./atlas.db`)
    no hay diferencia — reabrir el archivo ve el mismo contenido siempre.
    """
    connectable = config.attributes.get("connection", None)

    if connectable is None:
        connectable = engine_from_config(
            config.get_section(config.config_ini_section, {}),
            prefix="sqlalchemy.",
            poolclass=pool.NullPool,
        )

    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
