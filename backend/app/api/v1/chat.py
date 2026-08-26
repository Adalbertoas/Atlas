from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_db_session, get_orchestrator
from app.core.orchestrator import Orchestrator
from app.schemas.chat import ChatRequest, ChatResponse, ConfirmRequest, ConfirmResponse

router = APIRouter(prefix="/chat", tags=["chat"])


@router.post("", response_model=ChatResponse)
def send_message(
    body: ChatRequest,
    db: Session = Depends(get_db_session),
    orchestrator: Orchestrator = Depends(get_orchestrator),
) -> ChatResponse:
    result = orchestrator.handle_message(db, body.message, body.conversation_id)
    return ChatResponse(
        reply=result.reply,
        conversation_id=result.conversation_id,
        requires_confirmation=result.requires_confirmation,
        confirmation_id=result.confirmation_id,
        confirmation_description=result.confirmation_description,
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
    return ConfirmResponse(reply=result.reply or "")
