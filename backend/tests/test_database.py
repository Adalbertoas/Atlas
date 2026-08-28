"""Tests de app.core.database.init_db() — el cambio de create_all() manual a
Alembic (ver docstring de init_db) es infraestructura sensible: si se rompe,
ATLAS no arranca para nadie. Se prueba contra archivos sqlite reales en un
directorio temporal (no contra atlas.db ni contra la base de tests de
conftest, que usa su propio engine aparte vía dependency override) para
poder controlar el estado de la base antes de llamar a init_db().
"""
from __future__ import annotations

from sqlalchemy import create_engine, inspect

import app.core.database as db_module
from app.core.database import Base, init_db

# Registra los modelos en Base.metadata — necesario para el test que simula
# una base "pre-Alembic" con Base.metadata.create_all() directo. Mismo
# listado que usaba el init_db() viejo y que ahora usa migrations/env.py.
from app.automation import models as _automation_models  # noqa: F401
from app.core import usage as _usage_models  # noqa: F401
from app.memory import models as _memory_models  # noqa: F401
from app.notifications import models as _notifications_models  # noqa: F401
from app.personality import models as _personality_models  # noqa: F401
from app.reminders import models as _reminders_models  # noqa: F401
from app.security import audit as _audit_models  # noqa: F401
from app.smart_home import models as _smart_home_models  # noqa: F401


def _sqlite_engine(tmp_path, name: str):
    path = tmp_path / name
    return create_engine(f"sqlite:///{path}", connect_args={"check_same_thread": False})


def _use_engine(monkeypatch, engine) -> None:
    """init_db() lee `engine`/`settings` como nombres del módulo, no
    parámetros — se los reemplaza ahí para apuntar la corrida a una base de
    prueba en vez de la real del proceso."""
    monkeypatch.setattr(db_module, "engine", engine)
    monkeypatch.setattr(db_module.settings, "database_url", str(engine.url))


def test_init_db_creates_all_tables_on_a_fresh_database(tmp_path, monkeypatch):
    engine = _sqlite_engine(tmp_path, "fresh.db")
    _use_engine(monkeypatch, engine)

    init_db()

    tables = set(inspect(engine).get_table_names())
    assert "alembic_version" in tables
    for expected in (
        "conversation_messages",
        "memory_entries",
        "reminders",
        "audit_logs",
        "api_usage",
        "rooms",
        "routines",
    ):
        assert expected in tables

    # Las dos columnas que antes vivían en el parche manual
    # (_LATE_COLUMNS) ya vienen incluidas en la migración baseline.
    reminder_columns = {c["name"] for c in inspect(engine).get_columns("reminders")}
    assert "notified" in reminder_columns
    memory_columns = {c["name"] for c in inspect(engine).get_columns("memory_entries")}
    assert "embedding" in memory_columns


def test_init_db_is_idempotent(tmp_path, monkeypatch):
    """Dos llamadas seguidas (ej. dos arranques del backend sin cambios de
    esquema entre medio) no deben fallar — la segunda ya está en head."""
    engine = _sqlite_engine(tmp_path, "twice.db")
    _use_engine(monkeypatch, engine)

    init_db()
    init_db()  # no debería lanzar

    assert "conversation_messages" in inspect(engine).get_table_names()


def test_init_db_stamps_pre_alembic_databases_instead_of_recreating_tables(tmp_path, monkeypatch):
    """Una base creada antes de este cambio (vía Base.metadata.create_all(),
    sin Alembic — el mecanismo viejo) ya tiene todas las tablas: "aplicar" la
    migración baseline fallaría con "la tabla ya existe". init_db() debe
    detectar ese caso (tablas de ATLAS presentes, sin alembic_version) y
    marcarla como ya migrada (stamp) en vez de intentar recrearla."""
    engine = _sqlite_engine(tmp_path, "pre_alembic.db")
    _use_engine(monkeypatch, engine)

    Base.metadata.create_all(bind=engine)  # simula el mecanismo viejo
    assert "alembic_version" not in inspect(engine).get_table_names()

    init_db()  # no debería fallar con "table already exists"

    tables = set(inspect(engine).get_table_names())
    assert "alembic_version" in tables
    with engine.connect() as conn:
        version = conn.exec_driver_sql("SELECT version_num FROM alembic_version").scalar()
    assert version is not None


def test_init_db_upgrades_an_already_alembic_managed_database(tmp_path, monkeypatch):
    """Una base que ya pasó por Alembic antes (tiene alembic_version) debe
    ir por la rama de upgrade normal, no por stamp — es el camino que
    aplicaría futuras migraciones incrementales."""
    engine = _sqlite_engine(tmp_path, "already_managed.db")
    _use_engine(monkeypatch, engine)

    init_db()  # primera vez: crea todo + alembic_version
    with engine.connect() as conn:
        version_before = conn.exec_driver_sql("SELECT version_num FROM alembic_version").scalar()

    init_db()  # segunda vez: ya tiene alembic_version -> rama de upgrade

    with engine.connect() as conn:
        version_after = conn.exec_driver_sql("SELECT version_num FROM alembic_version").scalar()
    assert version_after == version_before
