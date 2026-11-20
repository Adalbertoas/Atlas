"""WebSocket del agente de la PC (ver app/agent/hub.py).

Se autentica con su propia clave (AGENT_TOKEN), distinta de la contraseña de
ATLAS: el agente ejecuta acciones en la PC y su clave solo sirve para esto.
"""
from __future__ import annotations

import hmac
import logging

from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect

from app.agent.hub import agent_hub
from app.config import get_settings
from app.security.auth import get_current_user

router = APIRouter(prefix="/agent", tags=["agent"])
logger = logging.getLogger(__name__)


def _authorized(websocket: WebSocket) -> bool:
    expected = get_settings().agent_token
    header = websocket.headers.get("authorization", "")
    token = header[7:] if header.lower().startswith("bearer ") else ""
    return bool(expected) and hmac.compare_digest(token.encode(), expected.encode())


@router.websocket("/ws")
async def agent_socket(websocket: WebSocket) -> None:
    if not _authorized(websocket):
        await websocket.close(code=4401)
        return
    await websocket.accept()
    host = None
    try:
        hello = await websocket.receive_json()
        host = str(hello.get("host") or "PC")[:80]
        await agent_hub.attach(websocket, host)
        logger.info("Agente de la PC conectado: %s", host)
        while True:
            await agent_hub.handle(await websocket.receive_json())
    except WebSocketDisconnect:
        pass
    finally:
        await agent_hub.detach(websocket)
        logger.info("Agente de la PC desconectado: %s", host)


@router.get("/status")
def agent_status(_user: str = Depends(get_current_user)) -> dict:
    return {"online": agent_hub.online, "host": agent_hub.host}
