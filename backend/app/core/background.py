"""Tareas periódicas en segundo plano (alertas del mundo, recordatorios).

Cada tarea es una función bloqueante que se ejecuta en un hilo aparte, para
que una consulta lenta a un servicio externo no congele el servidor. El
scheduler de rutinas (app/automation/scheduler.py) sigue con su propio loop.
"""
from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class _Job:
    name: str
    interval_seconds: float
    func: Callable[[], None]


class BackgroundJobs:
    def __init__(self) -> None:
        self._jobs: list[_Job] = []
        self._tasks: list[asyncio.Task] = []
        self._stop_event = asyncio.Event()

    def add(self, name: str, interval_seconds: float, func: Callable[[], None]) -> None:
        self._jobs.append(_Job(name, interval_seconds, func))

    def start(self) -> None:
        self._stop_event.clear()
        self._tasks = [asyncio.create_task(self._run(job)) for job in self._jobs]

    async def stop(self) -> None:
        self._stop_event.set()
        for task in self._tasks:
            try:
                await asyncio.wait_for(task, timeout=5)
            except (asyncio.TimeoutError, asyncio.CancelledError):
                task.cancel()
        self._tasks = []

    async def _run(self, job: _Job) -> None:
        while not self._stop_event.is_set():
            try:
                await asyncio.wait_for(self._stop_event.wait(), timeout=job.interval_seconds)
            except asyncio.TimeoutError:
                pass  # timeout normal: toca correr la tarea
            if self._stop_event.is_set():
                return
            try:
                await asyncio.to_thread(job.func)
            except Exception:  # noqa: BLE001 — una tarea rota no debe tumbar a las demás
                logger.exception("Error en la tarea en segundo plano '%s'", job.name)
