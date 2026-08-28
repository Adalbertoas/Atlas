from __future__ import annotations

import json
from collections.abc import Iterator

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.api.deps import get_db_session, get_orchestrator
from app.core.orchestrator import Orchestrator, StreamOutEvent
from app.schemas.chat import ChatRequest, ChatResponse, ConfirmRequest, ConfirmResponse
from app.security.rate_limit import chat_rate_limiter

router = APIRouter(prefix="/chat", tags=["chat"])


@router.post("", response_model=ChatResponse)
def send_message(
    body: ChatRequest,
    request: Request,
    db: Session = Depends(get_db_session),
    orchestrator: Orchestrator = Depends(get_orchestrator),
) -> ChatResponse:
    ip = request.client.host if request.client else "unknown"
    retry_after = chat_rate_limiter.check(ip)
    if retry_after > 0:
        raise HTTPException(
            status_code=429,
            detail="Demasiados mensajes en poco tiempo. Espera un momento.",
            headers={"Retry-After": str(round(retry_after))},
        )

    result = orchestrator.handle_message(db, body.message, body.conversation_id)
    return ChatResponse(
        reply=result.reply,
        conversation_id=result.conversation_id,
        requires_confirmation=result.requires_confirmation,
        confirmation_id=result.confirmation_id,
        confirmation_description=result.confirmation_description,
    )


def _sse_format(event: StreamOutEvent) -> str:
    """Un evento como Server-Sent Event: `event:` para que el cliente pueda
    filtrar por tipo sin parsear el JSON primero, `data:` con el resto.
    Los campos en None se omiten — mantiene el payload chico (la mayoría de
    los eventos "token" solo llevan `text`)."""
    payload = {
        "text": event.text,
        "tool_name": event.tool_name,
        "tool_description": event.tool_description,
        "conversation_id": event.conversation_id,
        "reply": event.reply,
        "confirmation_id": event.confirmation_id,
        "confirmation_description": event.confirmation_description,
    }
    payload = {k: v for k, v in payload.items() if v is not None}
    return f"event: {event.type}\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"


@router.post("/stream")
def send_message_stream(
    body: ChatRequest,
    request: Request,
    orchestrator: Orchestrator = Depends(get_orchestrator),
) -> StreamingResponse:
    """Como POST /chat, pero devuelve Server-Sent Events en vez de esperar
    la respuesta completa — el usuario ve el texto a medida que se genera,
    y "usando <tool>..." mientras corre una tool, en vez de silencio.

    No se puede usar `db: Session = Depends(get_db_session)` directo: esa
    sesión se cierra apenas esta función retorna el StreamingResponse, antes
    de que el generador de abajo se consuma de verdad (gotcha conocido de
    FastAPI con dependencias síncronas + respuestas en streaming — probado
    en vivo, rompía con "no such table" en los tests). En cambio se resuelve
    `get_db_session` a mano desde `request.app.dependency_overrides` (el
    mismo mecanismo que usa FastAPI puertas adentro) para poder abrir/cerrar
    la sesión con el ciclo de vida real del streaming, sin dejar de respetar
    el override que usan los tests (una base en memoria propia).
    """
    ip = request.client.host if request.client else "unknown"
    retry_after = chat_rate_limiter.check(ip)
    if retry_after > 0:
        raise HTTPException(
            status_code=429,
            detail="Demasiados mensajes en poco tiempo. Espera un momento.",
            headers={"Retry-After": str(round(retry_after))},
        )

    db_dependency = request.app.dependency_overrides.get(get_db_session, get_db_session)

    def _generate() -> Iterator[str]:
        db_gen = db_dependency()
        db = next(db_gen)
        try:
            for event in orchestrator.handle_message_stream(db, body.message, body.conversation_id):
                yield _sse_format(event)
        finally:
            db_gen.close()

    return StreamingResponse(_generate(), media_type="text/event-stream")


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
    return ConfirmResponse(reply=result.reply or "")
