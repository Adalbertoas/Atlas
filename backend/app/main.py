from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.router import api_router
from app.automation.engine import register_device_state_triggers
from app.automation.scheduler import AutomationScheduler
from app.config import get_settings
from app.core.database import init_db
from app.core.logging import configure_logging
from app.events.bus import event_bus, register_default_subscribers
from app.notifications.service import register_notification_subscriber
from app.reminders.scheduler import ReminderScheduler
from app.tools.registry import tool_registry


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    configure_logging(settings.log_level)
    init_db()
    register_default_subscribers()
    register_notification_subscriber(event_bus)
    register_device_state_triggers(tool_registry, event_bus)

    scheduler = AutomationScheduler(tool_registry, event_bus)
    scheduler.start()
    # Sin esto los recordatorios se podían crear y listar, pero nunca
    # avisaban al vencer — y un recordatorio que no interrumpe no sirve.
    reminders = ReminderScheduler(event_bus)
    reminders.start()
    try:
        yield
    finally:
        await scheduler.stop()
        await reminders.stop()


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
