from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.router import api_router
from app.automation.engine import register_device_state_triggers
from app.automation.scheduler import AutomationScheduler
from app.briefing.service import ensure_briefing_routine
from app.config import get_settings
from app.core.background import BackgroundJobs
from app.core.database import SessionLocal, init_db
from app.core.logging import configure_logging
from app.events.bus import event_bus, register_default_subscribers
from app.notifications.service import register_notification_subscriber
from app.reminders import service as reminders
from app.tools.registry import tool_registry
from app.world.alerts import check_due_alerts
from app.world.client import get_gods_eye_client


logger = logging.getLogger(__name__)

REMINDER_CHECK_SECONDS = 5  # resolución de los temporizadores
ALERT_CHECK_SECONDS = 60  # cada alerta tiene además su propio intervalo en minutos


def _fire_reminders() -> None:
    with SessionLocal() as db:
        reminders.fire_due(db, event_bus)


def _check_world_alerts() -> None:
    client = get_gods_eye_client()
    if client is None:
        return
    with SessionLocal() as db:
        check_due_alerts(db, client, event_bus)


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    configure_logging(settings.log_level)
    init_db()
    register_default_subscribers()
    register_notification_subscriber(event_bus)
    register_device_state_triggers(tool_registry, event_bus)

    with SessionLocal() as db:
        try:
            ensure_briefing_routine(db, settings.briefing_time)
        except ValueError:
            logger.warning("BRIEFING_TIME=%r no tiene formato HH:MM: se ignora.", settings.briefing_time)

    scheduler = AutomationScheduler(tool_registry, event_bus)
    scheduler.start()

    jobs = BackgroundJobs()
    jobs.add("recordatorios", REMINDER_CHECK_SECONDS, _fire_reminders)
    if get_gods_eye_client() is not None:
        jobs.add("alertas del mundo", ALERT_CHECK_SECONDS, _check_world_alerts)
    jobs.start()
    try:
        yield
    finally:
        await jobs.stop()
        await scheduler.stop()


def create_app() -> FastAPI:
    app = FastAPI(
        title="ATLAS",
        description="Núcleo del asistente personal ATLAS — API v1",
        version="0.1.0",
        lifespan=lifespan,
    )
    # CORS: la PWA móvil (Fase 7) corre en otro origen (puerto 5173) que el
    # backend (8000) — sin esto el navegador bloquea el fetch (visto en vivo:
    # "Failed to fetch" al intentar loguearse). Es un sistema personal sin
    # cookies de sesión (auth por Bearer token), así que abrir el origen no
    # expone nada que las credenciales del token ya no controlen.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(api_router)

    @app.get("/")
    def root() -> dict:
        return {"name": "ATLAS", "status": "online", "docs": "/docs"}

    return app


app = create_app()
