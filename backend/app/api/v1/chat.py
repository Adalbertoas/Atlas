from __future__ import annotations

import json
from collections.abc import Iterator

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.api.deps import get_db_session, get_orchestrator
from app.core.orchestrator import ChatResult, Orchestrator
from app.schemas.chat import ChatImage, ChatRequest, ChatResponse, ConfirmRequest, ConfirmResponse

router = APIRouter(prefix="/chat", tags=["chat"])


def _images(result: ChatResult) -> list[ChatImage]:
    return [ChatImage(mime_type=image.mime_type, data=image.data) for image in result.images]


def _to_response(result: ChatResult) -> ChatResponse:
    return ChatResponse(
        reply=result.reply,
        conversation_id=result.conversation_id,
        requires_confirmation=result.requires_confirmation,
        confirmation_id=result.confirmation_id,
        confirmation_description=result.confirmation_description,
        images=_images(result),
    )


@router.post("", response_model=ChatResponse)
def send_message(
    body: ChatRequest,
    db: Session = Depends(get_db_session),
    orchestrator: Orchestrator = Depends(get_orchestrator),
) -> ChatResponse:
    return _to_response(orchestrator.handle_message(db, body.message, body.conversation_id))


@router.post("/stream")
def stream_message(
    body: ChatRequest,
    db: Session = Depends(get_db_session),
    orchestrator: Orchestrator = Depends(get_orchestrator),
) -> StreamingResponse:
    """Igual que POST /chat, pero como Server-Sent Events: el texto llega a
    medida que el modelo lo genera. Cada evento es un JSON con `type`:
    start | delta | tool | done (este último trae lo mismo que ChatResponse)."""

    def events() -> Iterator[str]:
        try:
            for event in orchestrator.stream_message(db, body.message, body.conversation_id):
                payload: dict = {"type": event.type}
                if event.type == "start":
                    payload["conversation_id"] = event.conversation_id
                elif event.type == "delta":
                    payload["text"] = event.text
                elif event.type == "tool":
                    payload["name"] = event.name
                elif event.type == "done":
                    payload.update(_to_response(event.result).model_dump())
                yield f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"
        finally:
            # La dependencia de sesión puede cerrarse antes de que termine el
            # streaming; el generador la sigue usando, así que la cierra él.
            db.close()

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.post("/confirm", response_model=ConfirmResponse)
def confirm_action(
    body: ConfirmRequest,
    db: Session = Depends(get_db_session),
    orchestrator: Orchestrator = Depends(get_orchestrator),
) -> ConfirmResponse:
    if not body.approve:
        orchestrator.cancel_confirmation(body.confirmation_id)
        return ConfirmResponse(reply="Acción cancelada.")

    result = orchestrator.execute_confirmed(db, body.confirmation_id)
    return ConfirmResponse(reply=result.reply or "", images=_images(result))
