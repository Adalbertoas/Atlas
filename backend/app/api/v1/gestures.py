"""Control de mouse por gestos, recibido por WebSocket desde el celular
(la detección de la mano corre en el navegador — acá solo llegan
coordenadas, nunca video). No pasa por el Orchestrator/Permission Manager:
es entrada de bajo nivel, igual que un mouse físico.
"""
from __future__ import annotations

import json

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.gestures.mouse_controller import MouseController
from app.security.auth import is_token_valid

router = APIRouter(prefix="/gestures", tags=["gestures"])


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
            except (json.JSONDecodeError, KeyError, ValueError, TypeError):
                continue  # frame inválido: se ignora, no se corta la conexión
    except WebSocketDisconnect:
        pass
    finally:
        controller.release()  # nunca dejar el clic apretado si la conexión se corta
