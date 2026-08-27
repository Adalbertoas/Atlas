from __future__ import annotations

from fastapi import APIRouter, Depends

from app.api.v1 import (
    auth,
    automations,
    chat,
    devices,
    gestures,
    memory,
    music,
    notifications,
    reminders,
    rooms,
    settings,
    system,
    tools,
    vision,
    voice,
)
from app.security.auth import get_current_user

api_router = APIRouter(prefix="/api/v1")

# Público (sin login): autenticarse, y el chequeo básico de "¿está vivo el servidor?".
api_router.include_router(auth.router)
api_router.include_router(system.router)  # /health es público; /status exige login por endpoint (ver system.py)

# Todo lo demás requiere estar logueado — protegido a nivel de router en vez
# de endpoint por endpoint, para no tener que tocar cada función y no
# olvidarse de ninguna sin querer.
_protected = Depends(get_current_user)
api_router.include_router(chat.router, dependencies=[_protected])
api_router.include_router(memory.router, dependencies=[_protected])
api_router.include_router(tools.router, dependencies=[_protected])
api_router.include_router(settings.router, dependencies=[_protected])
api_router.include_router(voice.router, dependencies=[_protected])
api_router.include_router(rooms.router, dependencies=[_protected])
api_router.include_router(devices.router, dependencies=[_protected])
api_router.include_router(automations.router, dependencies=[_protected])
api_router.include_router(notifications.router)  # ya protegido endpoint por endpoint (ver notifications.py)
api_router.include_router(vision.router, dependencies=[_protected])
api_router.include_router(music.router, dependencies=[_protected])
api_router.include_router(reminders.router, dependencies=[_protected])

# El WebSocket de gestos se autentica solo (el primer mensaje trae el
# token) — HTTPBearer (usado por get_current_user) no aplica a handshakes
# de WebSocket del navegador, que no pueden mandar headers custom.
api_router.include_router(gestures.router)
