"""Orchestrator: el cerebro de ATLAS (sección 22 del prompt maestro).

Flujo:
    Usuario -> Comprensión de intención -> Planificación (delegado al AIProvider
    vía tool calling) -> Selección de herramienta -> Permission Manager ->
    Ejecución -> Resultado -> Memoria/Eventos -> Respuesta al usuario.

Fase 2 agrega: memoria de conversación multi-turno, personalidad configurable
(reemplaza el SYSTEM_PROMPT fijo de la V1) y publicación de eventos en el
Event Bus.
"""
from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.ai.base import AIMessage, AIProvider
from app.events.bus import Event, EventBus, EventType
from app.memory.conversation_service import append_message, get_history
from app.personality.service import build_system_prompt, get_profile
from app.security.audit import write_audit
from app.security.permissions import PermissionManager
from app.tools.base import ToolContext
from app.tools.registry import ToolRegistry

logger = logging.getLogger(__name__)

MAX_TOOL_ITERATIONS = 4  # evita loops infinitos si la IA insiste en llamar tools
HISTORY_LIMIT = 20  # mensajes previos que se reinyectan como contexto


@dataclass
class ChatResult:
    reply: str | None
    conversation_id: str
    requires_confirmation: bool = False
    confirmation_id: str | None = None
    confirmation_description: str | None = None


class Orchestrator:
    def __init__(
        self,
        ai_provider: AIProvider,
        registry: ToolRegistry,
        permissions: PermissionManager,
        events: EventBus,
    ) -> None:
        self._ai = ai_provider
        self._registry = registry
        self._permissions = permissions
        self._events = events

    def handle_message(self, db: Session, user_message: str, conversation_id: str | None = None) -> ChatResult:
        conversation_id = conversation_id or str(uuid.uuid4())

        self._events.publish(
            Event(
                type=EventType.USER_COMMAND,
                payload={"conversation_id": conversation_id, "message": user_message},
            )
        )

        # El mensaje del usuario queda registrado apenas llega, aunque la
        # respuesta final todavía no se conozca (ej. si termina pidiendo
        # confirmación de una acción de riesgo medio).
        append_message(db, conversation_id, "user", user_message)

        personality = get_profile(db)
        history = get_history(db, conversation_id, limit=HISTORY_LIMIT)

        messages: list[AIMessage] = [AIMessage(role="system", content=build_system_prompt(personality))]
        # El último mensaje de `history` es el que acabamos de guardar arriba;
        # se reinyecta como el turno "user" actual, no duplicado.
        messages += [AIMessage(role=m.role, content=m.content) for m in history]

        tool_schemas = self._registry.to_ai_schemas()

        for _ in range(MAX_TOOL_ITERATIONS):
            try:
                response = self._ai.chat(messages, tools=tool_schemas)
            except Exception as exc:  # noqa: BLE001 — nunca dejar caer un 500 crudo por un fallo del proveedor de IA
                logger.exception("Fallo al llamar al AIProvider")
                reply = f"No pude conectar con la IA en este momento ({exc})."
                append_message(db, conversation_id, "assistant", reply)
                return ChatResult(reply=reply, conversation_id=conversation_id)

            if not response.wants_tool_call:
                reply = response.text or ""
                append_message(db, conversation_id, "assistant", reply)
                return ChatResult(reply=reply, conversation_id=conversation_id)

            # V1/Fase 2: se resuelve un tool_call a la vez (suficiente para las tools base).
            call = response.tool_calls[0]

            # El turno del modelo que pidió la tool debe quedar en el historial
            # antes de su resultado (algunos proveedores, como Anthropic, lo exigen).
            messages.append(AIMessage(role="assistant", content=response.text or "", tool_calls=[call]))

            tool = self._registry.get(call.name)
            if tool is None:
                messages.append(
                    AIMessage(
                        role="tool",
                        content=f"Error: la herramienta '{call.name}' no existe.",
                        tool_call_id=call.id,
                        name=call.name,
                    )
                )
                continue

            decision = self._permissions.evaluate(
                tool_name=tool.name,
                risk_level=tool.resolve_risk_level(call.arguments),
                parameters=call.arguments,
                human_description=tool.human_description(call.arguments),
                conversation_id=conversation_id,
            )

            if decision.requires_confirmation:
                # No se persiste turno de "assistant" todavía: la conversación
                # sigue abierta hasta que el usuario confirme o cancele.
                return ChatResult(
                    reply=None,
                    conversation_id=conversation_id,
                    requires_confirmation=True,
                    confirmation_id=decision.pending.id,
                    confirmation_description=decision.pending.description,
                )

            result = tool.execute(call.arguments, ToolContext(db=db))
            write_audit(
                db,
                tool_name=tool.name,
                parameters=call.arguments,
                risk_level=tool.resolve_risk_level(call.arguments).value,
                result_summary=result.as_text(),
                success=result.success,
            )

            messages.append(
                AIMessage(role="tool", content=result.as_text(), tool_call_id=call.id, name=call.name)
            )

        logger.warning("Se alcanzó MAX_TOOL_ITERATIONS sin respuesta final del modelo.")
        reply = "No pude completar la solicitud, intenta reformularla."
        append_message(db, conversation_id, "assistant", reply)
        return ChatResult(reply=reply, conversation_id=conversation_id)

    def cancel_confirmation(self, confirmation_id: str) -> None:
        self._permissions.resolve(confirmation_id)

    def execute_confirmed(self, db: Session, confirmation_id: str) -> ChatResult:
        pending = self._permissions.resolve(confirmation_id)
        if pending is None:
            return ChatResult(reply="Esa confirmación ya no es válida o expiró.", conversation_id="")

        conversation_id = pending.conversation_id or str(uuid.uuid4())
        tool = self._registry.get(pending.tool_name)
        if tool is None:
            reply = f"La herramienta '{pending.tool_name}' ya no existe."
            append_message(db, conversation_id, "assistant", reply)
            return ChatResult(reply=reply, conversation_id=conversation_id)

        result = tool.execute(pending.parameters, ToolContext(db=db))
        write_audit(
            db,
            tool_name=tool.name,
            parameters=pending.parameters,
            risk_level=pending.risk_level.value,
            result_summary=result.as_text(),
            success=result.success,
        )
        reply = result.as_text()
        append_message(db, conversation_id, "assistant", reply)
        return ChatResult(reply=reply, conversation_id=conversation_id)
