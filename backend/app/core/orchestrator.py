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
from collections.abc import Iterator
from dataclasses import dataclass, field

from sqlalchemy.orm import Session

from app.ai.base import AIMessage, AIProvider, AIResponse
from app.events.bus import Event, EventBus, EventType
from app.memory.conversation_service import append_message, get_history
from app.personality.service import build_system_prompt, get_profile
from app.security.audit import write_audit
from app.security.permissions import PermissionManager
from app.tools.base import ToolContext, ToolImage
from app.tools.registry import ToolRegistry

logger = logging.getLogger(__name__)

MAX_TOOL_ITERATIONS = 6  # vueltas al modelo; evita loops infinitos si la IA insiste en llamar tools
HISTORY_LIMIT = 20  # mensajes previos que se reinyectan como contexto


@dataclass
class ChatResult:
    reply: str | None
    conversation_id: str
    requires_confirmation: bool = False
    confirmation_id: str | None = None
    confirmation_description: str | None = None
    # Imágenes que devolvieron las tools de este pedido (ej. un mapa de radar).
    images: list[ToolImage] = field(default_factory=list)


@dataclass
class ChatEvent:
    """Un paso del procesamiento de un mensaje, para el chat en streaming.

    type: "start" (trae conversation_id) | "delta" (texto parcial del modelo) |
    "tool" (se está por ejecutar la tool `name`) | "done" (trae `result`).
    """

    type: str
    conversation_id: str | None = None
    text: str | None = None
    name: str | None = None
    result: ChatResult | None = None


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
        result: ChatResult | None = None
        for event in self.stream_message(db, user_message, conversation_id):
            if event.type == "done":
                result = event.result
        assert result is not None  # stream_message siempre termina con "done"
        return result

    def stream_message(
        self, db: Session, user_message: str, conversation_id: str | None = None
    ) -> Iterator[ChatEvent]:
        """Procesa un mensaje emitiendo cada paso; el último evento es siempre "done"."""
        conversation_id = conversation_id or str(uuid.uuid4())
        yield ChatEvent(type="start", conversation_id=conversation_id)

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
        images: list[ToolImage] = []

        def finish(reply: str) -> ChatEvent:
            append_message(db, conversation_id, "assistant", reply)
            return ChatEvent(
                type="done", result=ChatResult(reply=reply, conversation_id=conversation_id, images=images)
            )

        for _ in range(MAX_TOOL_ITERATIONS):
            response: AIResponse | None = None
            try:
                for chunk in self._ai.chat_stream(messages, tools=tool_schemas):
                    if isinstance(chunk, AIResponse):
                        response = chunk
                    elif chunk:
                        yield ChatEvent(type="delta", text=chunk)
            except Exception as exc:  # noqa: BLE001 — nunca dejar caer un 500 crudo por un fallo del proveedor de IA
                logger.exception("Fallo al llamar al AIProvider")
                yield finish(f"No pude conectar con la IA en este momento ({exc}).")
                return
            if response is None:
                yield finish("La IA no devolvió ninguna respuesta.")
                return

            if not response.wants_tool_call:
                yield finish(response.text or "")
                return

            # El turno del modelo que pidió las tools debe quedar en el historial
            # antes de sus resultados (algunos proveedores, como Anthropic, lo exigen).
            messages.append(
                AIMessage(role="assistant", content=response.text or "", tool_calls=list(response.tool_calls))
            )

            # Un mismo turno puede pedir varias tools ("apagá la luz y poné
            # música"): se resuelven todas, en orden, antes de volver al modelo.
            for call in response.tool_calls:
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
                    # sigue abierta hasta que el usuario confirme o cancele. Las
                    # tools anteriores del mismo turno ya se ejecutaron; las que
                    # venían después de esta no se ejecutan.
                    yield ChatEvent(
                        type="done",
                        result=ChatResult(
                            reply=None,
                            conversation_id=conversation_id,
                            requires_confirmation=True,
                            confirmation_id=decision.pending.id,
                            confirmation_description=decision.pending.description,
                            images=images,
                        ),
                    )
                    return

                yield ChatEvent(type="tool", name=tool.name)
                result = tool.execute(call.arguments, ToolContext(db=db))
                images.extend(result.images)
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
        yield finish("No pude completar la solicitud, intenta reformularla.")

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
        return ChatResult(reply=reply, conversation_id=conversation_id, images=list(result.images))
