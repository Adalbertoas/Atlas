"""Backups automáticos de la base de datos (Fase 26).

Hueco real: `atlas.db` es un solo archivo SQLite con memoria, recordatorios,
automatizaciones, notificaciones y auditoría — todo junto, sin ninguna
copia de seguridad. Si el archivo se corrompe (un apagado brusco a mitad de
escritura, un disco que falla), se pierde todo de una sola vez.

Usa `sqlite3.Connection.backup()` (API online de backup de SQLite) en vez
de copiar el archivo con `shutil.copy`: una copia de archivo cruda mientras
hay escrituras en curso puede capturar un estado a medio escribir y quedar
corrupta; el backup online de SQLite es seguro incluso con la base en uso.

Solo aplica a SQLite (DATABASE_URL por defecto). Si el proyecto migra a
PostgreSQL (ver docs/architecture.md), esto no sirve — se avisa en vez de
fallar en silencio, mismo criterio que la temperatura de CPU en la Fase 11:
sin poder dar el dato/la función real, no se finge que se está cumpliendo.
"""
from __future__ import annotations

import asyncio
import logging
import sqlite3
from datetime import datetime
from pathlib import Path

from app.config import get_settings

logger = logging.getLogger(__name__)

_SQLITE_PREFIX = "sqlite:///"


def _sqlite_path() -> Path | None:
    """None si DATABASE_URL no es SQLite — backups no aplican."""
    url = get_settings().database_url
    if not url.startswith(_SQLITE_PREFIX):
        return None
    return Path(url[len(_SQLITE_PREFIX) :])


def perform_backup() -> Path | None:
    """Hace un backup y aplica rotación. Devuelve la ruta del backup nuevo,
    o None si no corresponde (no es SQLite, o la base todavía no existe —
    ej. primer arranque antes de que init_db() la cree)."""
    settings = get_settings()
    source_path = _sqlite_path()
    if source_path is None:
        logger.info("Backups automáticos: DATABASE_URL no es SQLite, se omite (ver docs/architecture.md).")
        return None
    if not source_path.exists():
        return None

    backup_dir = Path(settings.backup_dir)
    backup_dir.mkdir(parents=True, exist_ok=True)

    # Microsegundos incluidos: dos backups en el mismo segundo (poco
    # probable en uso normal, pero pasa seguro en los tests) no deben
    # generar el mismo nombre de archivo y pisarse entre sí.
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    destination_path = backup_dir / f"{source_path.stem}_{timestamp}.db"

    source_conn = sqlite3.connect(str(source_path))
    try:
        destination_conn = sqlite3.connect(str(destination_path))
        try:
            source_conn.backup(destination_conn)
        finally:
            destination_conn.close()
    finally:
        source_conn.close()

    logger.info("Backup de la base de datos creado: %s", destination_path)
    _rotate_backups(backup_dir, source_path.stem, settings.backup_keep_count)
    return destination_path


def _rotate_backups(backup_dir: Path, stem: str, keep_count: int) -> None:
    backups = sorted(backup_dir.glob(f"{stem}_*.db"), key=lambda p: p.stat().st_mtime, reverse=True)
    for stale in backups[keep_count:]:
        stale.unlink(missing_ok=True)


class BackupScheduler:
    """Mismo patrón que ReminderScheduler/AutomationScheduler: una tarea en
    background del propio proceso — para un solo usuario en una sola PC no
    hace falta nada más pesado (cron del SO, Task Scheduler de Windows)."""

    def __init__(self) -> None:
        self._task: asyncio.Task | None = None
        self._stop_event = asyncio.Event()

    def start(self) -> None:
        settings = get_settings()
        if not settings.backup_enabled:
            return
        self._stop_event.clear()
        self._task = asyncio.create_task(self._loop())

    async def stop(self) -> None:
        self._stop_event.set()
        if self._task is not None:
            try:
                await asyncio.wait_for(self._task, timeout=5)
            except (asyncio.TimeoutError, asyncio.CancelledError):
                self._task.cancel()
            self._task = None

    async def _loop(self) -> None:
        # Backup inmediato al arrancar: si el proceso corre pocas horas por
        # vez (un asistente de escritorio, no un servidor 24/7), esperar el
        # intervalo completo dejaría pasar días sin ningún backup nuevo.
        self._run_backup_safely()

        interval_seconds = get_settings().backup_interval_hours * 3600
        while not self._stop_event.is_set():
            try:
                await asyncio.wait_for(self._stop_event.wait(), timeout=interval_seconds)
            except asyncio.TimeoutError:
                pass
            if self._stop_event.is_set():
                return
            self._run_backup_safely()

    def _run_backup_safely(self) -> None:
        try:
            perform_backup()
        except Exception:  # noqa: BLE001 — el scheduler NUNCA debe morir en silencio
            logger.exception("Error haciendo backup de la base de datos")
