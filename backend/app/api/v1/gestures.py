"""Control de mouse por gestos, recibido por WebSocket desde el celular
(la detección de la mano corre en el navegador — acá solo llegan
coordenadas, nunca video). No pasa por el Orchestrator/Permission Manager:
es entrada de bajo nivel, igual que un mouse físico.
"""
from __future__ import annotations

import json

from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect

from app.gestures.mouse_controller import MouseController
from app.gestures.session import gesture_session
from app.security.auth import get_current_user, is_token_valid

router = APIRouter(prefix="/gestures", tags=["gestures"])


@router.get("/status")
def status(_user: str = Depends(get_current_user)) -> dict:
    """Estado en vivo del receptor de gestos, para el dashboard (Fase 13).

    El dashboard corre en la PC controlada — la cámara está en el celular,
    así que lo único que puede mostrar es si hay un celular conectado."""
    state = gesture_session.snapshot()
    return {
        "connected": state.connected,
        "connected_since": state.connected_since.isoformat() if state.connected_since else None,
        "last_event_at": state.last_event_at.isoformat() if state.last_event_at else None,
        "events_received": state.events_received,
    }


@router.websocket("/stream")
async def gestures_stream(websocket: WebSocket) -> None:
    await websocket.accept()

    # Los WebSocket del navegador no soportan headers custom (Authorization)
    # al conectar — se manda el token como primer mensaje en su lugar.
    try:
        first_message = await websocket.receive_text()
        auth_payload = json.loads(first_message)
        token = auth_payload.get("token", "")
    except (json.JSONDecodeError, KeyError):
        token = ""

    if not is_token_valid(token):
        await websocket.close(code=4401)  # 4401: código custom, "no autorizado"
        return

    controller = MouseController()
    gesture_session.connected()
    try:
        while True:
            raw = await websocket.receive_text()
            try:
                data = json.loads(raw)
                if "scroll" in data:
                    controller.scroll(float(data["scroll"]))
                else:
                    controller.update(
                        x_norm=float(data["x"]),
                        y_norm=float(data["y"]),
                        pinching=bool(data.get("pinching", False)),
                    )
                gesture_session.record_event()
            except (json.JSONDecodeError, KeyError, ValueError, TypeError):
                continue  # frame inválido: se ignora, no se corta la conexión
    except WebSocketDisconnect:
        pass
    finally:
        controller.release()  # nunca dejar el clic apretado si la conexión se corta
        gesture_session.disconnected()
