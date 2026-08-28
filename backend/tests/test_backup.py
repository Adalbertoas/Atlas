"""Tests de backups automáticos (Fase 26). Usan un archivo SQLite real en
un directorio temporal — no tocan backend/atlas.db."""
from __future__ import annotations

import sqlite3

from app.core.backup import perform_backup


def _make_sqlite_db(path) -> None:
    conn = sqlite3.connect(str(path))
    conn.execute("CREATE TABLE t (id INTEGER PRIMARY KEY, value TEXT)")
    conn.execute("INSERT INTO t (value) VALUES ('hola')")
    conn.commit()
    conn.close()


def _configure(monkeypatch, tmp_path, db_name="atlas.db", **overrides):
    from app.config import get_settings

    db_path = tmp_path / db_name
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path}")
    monkeypatch.setenv("BACKUP_DIR", str(tmp_path / "backups"))
    for key, value in overrides.items():
        monkeypatch.setenv(key.upper(), str(value))
    get_settings.cache_clear()
    return db_path


def test_perform_backup_creates_a_copy(tmp_path, monkeypatch):
    db_path = _configure(monkeypatch, tmp_path)
    _make_sqlite_db(db_path)

    backup_path = perform_backup()

    assert backup_path is not None
    assert backup_path.exists()
    conn = sqlite3.connect(str(backup_path))
    rows = conn.execute("SELECT value FROM t").fetchall()
    conn.close()
    assert rows == [("hola",)]

    from app.config import get_settings

    get_settings.cache_clear()


def test_perform_backup_returns_none_when_db_missing(tmp_path, monkeypatch):
    _configure(monkeypatch, tmp_path)
    # No se creó el archivo: simula el primer arranque antes de init_db().
    assert perform_backup() is None

    from app.config import get_settings

    get_settings.cache_clear()


def test_perform_backup_returns_none_for_non_sqlite(tmp_path, monkeypatch):
    from app.config import get_settings

    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg2://user:pass@localhost/atlas")
    get_settings.cache_clear()

    assert perform_backup() is None

    get_settings.cache_clear()


def test_backup_rotation_keeps_only_the_newest(tmp_path, monkeypatch):
    db_path = _configure(monkeypatch, tmp_path, backup_keep_count=2)
    _make_sqlite_db(db_path)

    for _ in range(4):
        perform_backup()

    from app.config import get_settings

    backup_dir = tmp_path / "backups"
    remaining = list(backup_dir.glob("atlas_*.db"))
    assert len(remaining) == 2

    get_settings.cache_clear()
