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
from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.ai.base import AIMessage, AIProvider
from app.config import get_settings
from app.core.usage import check_budget, record_usage
from app.events.bus import Event, EventBus, EventType
from app.memory.conversation_service import append_message, get_history
from app.personality.service import build_system_prompt, get_profile
from app.security.audit import write_audit
from app.security.permissions import PermissionManager
from app.tools.base import ToolContext
from app.tools.registry import ToolRegistry

logger = logging.getLogger(__name__)

MAX_TOOL_ITERATIONS = 4  # evita loops infinitos si la IA insiste en llamar tools

# Antes: HISTORY_LIMIT = 20 mensajes, sin importar su tamaño. 20 mensajes
# cortos ("sí"/"anotado") no pesan lo mismo que 20 mensajes largos (una
# respuesta de ATLAS citando una búsqueda web) — con Claude real eso podía
# inflar tokens/costo de un turno a otro sin que nada lo mostrara. Ahora se
# acota por tamaño estimado, no por cantidad.
HISTORY_FETCH_LIMIT = 60  # techo de mensajes a traer de la DB antes de recortar por tokens
HISTORY_TOKEN_BUDGET = 6000  # tokens estimados de historial a reinyectar como contexto
# No hay tokenizer real de Anthropic disponible sin pegarle a la API (su SDK
# no trae uno local, a diferencia de tiktoken en OpenAI) — 4 caracteres por
# token es la aproximación estándar para texto en inglés/español, la misma
# clase de estimación que ya usa app/core/usage.py para el costo.
CHARS_PER_TOKEN_ESTIMATE = 4


def _trim_history_to_token_budget(history: list, budget_tokens: int) -> list:
    """Descarta los mensajes más viejos hasta que el total estimado entre
    dentro del presupuesto. Siempre conserva al menos el último mensaje
    (el turno actual del usuario), aunque él solo exceda el presupuesto —
    cortarlo dejaría a ATLAS sin poder ver lo que se le acaba de pedir."""
    if not history:
        return history

    kept: list = []
    total_chars = 0
    budget_chars = budget_tokens * CHARS_PER_TOKEN_ESTIMATE

    for message in reversed(history):
        message_chars = len(message.content or "")
        if kept and total_chars + message_chars > budget_chars:
            break
        kept.append(message)
        total_chars += message_chars

    kept.reverse()
    return kept


@dataclass
class ChatResult:
    reply: str | None
    conversation_id: str
    requires_confirmation: bool = False
    confirmation_id: str | None = None
    confirmation_description: str | None = None


@dataclass
class StreamOutEvent:
    """Un evento del streaming de handle_message_stream, ya en API pública
    (a diferencia de StreamEvent de app/ai/base.py, que es interno entre el
    Orchestrator y el AIProvider).

    - "token": fragmento de texto de la respuesta, a medida que se genera.
    - "tool_call": ATLAS está por ejecutar una tool (para mostrar "usando
      <tool>..." en vivo, no como confirmación — estas ya están aprobadas).
    - "confirmation": el turno quedó pendiente de que el usuario confirme
      una acción de riesgo medio/alto (mismo significado que
      ChatResult.requires_confirmation).
    - "done": el turno terminó con una respuesta final de texto.
    """

    type: str  # "token" | "tool_call" | "confirmation" | "done"
    text: str | None = None
    tool_name: str | None = None
    tool_description: str | None = None
    conversation_id: str | None = None
    reply: str | None = None
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
        history = get_history(db, conversation_id, limit=HISTORY_FETCH_LIMIT)
        history = _trim_history_to_token_budget(history, HISTORY_TOKEN_BUDGET)

        messages: list[AIMessage] = [AIMessage(role="system", content=build_system_prompt(personality))]
        # El último mensaje de `history` es el que acabamos de guardar arriba;
        # se reinyecta como el turno "user" actual, no duplicado.
        messages += [AIMessage(role=m.role, content=m.content) for m in history]

        tool_schemas = self._registry.to_ai_schemas()

        for _ in range(MAX_TOOL_ITERATIONS):
            # Antes de cada llamada real, no solo al principio: un loop de
            # tool calling insistente también gasta, y el chequeo tiene que
            # frenarlo a mitad de turno, no solo en el siguiente mensaje.
            budget = check_budget(db)
            if budget.exceeded:
                reply = budget.reason
                append_message(db, conversation_id, "assistant", reply)
                return ChatResult(reply=reply, conversation_id=conversation_id)

            try:
                response = self._ai.chat(messages, tools=tool_schemas)
            except Exception:  # noqa: BLE001 — nunca dejar caer un 500 crudo por un fallo del proveedor de IA
                # El detalle de la excepción va solo al log, nunca a la respuesta:
                # puede traer texto de headers/URLs del proveedor de IA que no
                # aporta nada al usuario y no conviene exponer.
                logger.exception("Fallo al llamar al AIProvider")
                reply = "No pude conectar con la IA en este momento. Intenta de nuevo en un momento."
                append_message(db, conversation_id, "assistant", reply)
                return ChatResult(reply=reply, conversation_id=conversation_id)

            if response.input_tokens or response.output_tokens:
                record_usage(
                    db,
                    model=get_settings().anthropic_model,
                    input_tokens=response.input_tokens,
                    output_tokens=response.output_tokens,
                )

            if not response.wants_tool_call:
                reply = response.text or ""
                append_message(db, conversation_id, "assistant", reply)
                return ChatResult(reply=reply, conversation_id=conversation_id)

            # Se resuelven todos los tool_calls que pidió el modelo en este
            # turno, no solo el primero (antes: limitante real si el modelo
            # pedía varias tools de una — el resto del lote se perdía sin
            # ejecutarse ni avisar).
            calls = response.tool_calls

            # El turno del modelo que pidió la(s) tool(s) debe quedar en el
            # historial antes de sus resultados (algunos proveedores, como
            # Anthropic, lo exigen) — un solo mensaje "assistant" con todos
            # los tool_calls del turno, no uno por call.
            messages.append(AIMessage(role="assistant", content=response.text or "", tool_calls=calls))

            resolved, missing_tool_messages, pending_confirmation = self._evaluate_tool_calls(
                calls, conversation_id
            )

            if pending_confirmation is not None:
                # No se persiste ni se ejecuta nada de este turno todavía: la
                # conversación sigue abierta hasta que el usuario confirme o
                # cancele. Si había otros tool_calls en el mismo lote, quedan
                # sin resolver — se vuelven a pedir en el siguiente turno si
                # todavía hacen falta, en vez de ejecutar a mitad de un turno
                # que no terminó.
                return ChatResult(
                    reply=None,
                    conversation_id=conversation_id,
                    requires_confirmation=True,
                    confirmation_id=pending_confirmation.pending.id,
                    confirmation_description=pending_confirmation.pending.description,
                )

            # Se agota el generador sin mirar lo que yieldea: handle_message
            # no necesita avisar "usando <tool>..." en vivo, eso es lo que
            # aprovecha handle_message_stream más abajo.
            for _ in self._execute_resolved_calls(resolved, missing_tool_messages, messages, db):
                pass

        logger.warning("Se alcanzó MAX_TOOL_ITERATIONS sin respuesta final del modelo.")
        reply = "No pude completar la solicitud, intenta reformularla."
        append_message(db, conversation_id, "assistant", reply)
        return ChatResult(reply=reply, conversation_id=conversation_id)

    def _evaluate_tool_calls(
        self, calls: list, conversation_id: str
    ) -> tuple[list[tuple], list[AIMessage], object | None]:
        """Evalúa el permiso de cada tool_call sin ejecutar nada todavía.
        Compartido por handle_message y handle_message_stream para que las
        dos versiones (síncrona y streaming) nunca puedan divergir en esta
        decisión, que es la parte sensible (qué se ejecuta solo y qué pide
        confirmación).

        Devuelve (resolved, missing_tool_messages, pending_confirmation):
        - resolved: [(call, tool), ...] ya aprobados, listos para ejecutar.
        - missing_tool_messages: AIMessages de error para calls a tools que
          ya no existen (el registry cambió entre que el modelo las vio y
          las pidió — no debería pasar en la práctica, pero si pasa no debe
          romper el turno entero).
        - pending_confirmation: la decisión que exige confirmación, o None
          si ninguna la necesita. Si no es None, `resolved` puede tener
          calls previos del mismo lote que quedaron sin ejecutar a
          propósito (ver handle_message: todo o nada por turno).
        """
        resolved: list[tuple] = []
        missing_tool_messages: list[AIMessage] = []
        pending_confirmation = None

        for call in calls:
            tool = self._registry.get(call.name)
            if tool is None:
                missing_tool_messages.append(
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
                pending_confirmation = decision
                break
            resolved.append((call, tool))

        return resolved, missing_tool_messages, pending_confirmation

    def _execute_resolved_calls(
        self,
        resolved: list[tuple],
        missing_tool_messages: list[AIMessage],
        messages: list[AIMessage],
        db: Session,
    ) -> Iterator[tuple]:
        """Ejecuta las tools ya aprobadas, escribe auditoría, y agrega el
        tool_result de cada una a `messages` (mutado in-place). Generador:
        yieldea (tool, call) *antes* de ejecutar cada una — handle_message
        lo agota sin mirar el valor (no necesita avisar nada en vivo);
        handle_message_stream sí lo consume, para emitir un evento
        "usando <tool>..." mientras corre."""
        messages += missing_tool_messages
        for call, tool in resolved:
            yield tool, call
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

    def handle_message_stream(
        self, db: Session, user_message: str, conversation_id: str | None = None
    ) -> Iterator[StreamOutEvent]:
        """Como handle_message, pero entregando la respuesta a medida que se
        genera en vez de recién al final. Misma lógica de presupuesto,
        resolución de tool_calls y confirmación (compartida vía
        _evaluate_tool_calls/_execute_resolved_calls) — lo único que cambia
        es que cada llamada al modelo usa chat_stream() en vez de chat(), y
        cada delta de texto se reenvía como evento apenas llega.

        El texto acumulado de *todas* las iteraciones (no solo la última) es
        lo que se persiste y se devuelve como respuesta final: si el modelo
        dijo algo antes de pedir una tool ("Reviso el clima..."), ese texto
        ya se le mostró al usuario en vivo, y descartarlo del historial
        dejaría un desfasaje entre lo que vio y lo que queda guardado.
        """
        conversation_id = conversation_id or str(uuid.uuid4())

        self._events.publish(
            Event(
                type=EventType.USER_COMMAND,
                payload={"conversation_id": conversation_id, "message": user_message},
            )
        )
        append_message(db, conversation_id, "user", user_message)

        personality = get_profile(db)
        history = get_history(db, conversation_id, limit=HISTORY_FETCH_LIMIT)
        history = _trim_history_to_token_budget(history, HISTORY_TOKEN_BUDGET)

        messages: list[AIMessage] = [AIMessage(role="system", content=build_system_prompt(personality))]
        messages += [AIMessage(role=m.role, content=m.content) for m in history]

        tool_schemas = self._registry.to_ai_schemas()
        accumulated_text: list[str] = []

        for _ in range(MAX_TOOL_ITERATIONS):
            budget = check_budget(db)
            if budget.exceeded:
                reply = budget.reason
                append_message(db, conversation_id, "assistant", reply)
                yield StreamOutEvent(type="done", conversation_id=conversation_id, reply=reply)
                return

            response = None
            try:
                for chunk in self._ai.chat_stream(messages, tools=tool_schemas):
                    if chunk.type == "delta" and chunk.text:
                        accumulated_text.append(chunk.text)
                        yield StreamOutEvent(type="token", text=chunk.text)
                    elif chunk.type == "final":
                        response = chunk.response
            except Exception:  # noqa: BLE001 — mismo criterio que handle_message
                logger.exception("Fallo al llamar al AIProvider (streaming)")
                reply = "No pude conectar con la IA en este momento. Intenta de nuevo en un momento."
                append_message(db, conversation_id, "assistant", reply)
                yield StreamOutEvent(type="done", conversation_id=conversation_id, reply=reply)
                return

            if response is None:
                # No debería pasar (todo chat_stream, incluido el fallback
                # por defecto de AIProvider, siempre termina en un evento
                # "final") — guardarraíl, no un caso esperado.
                logger.error("chat_stream terminó sin emitir un evento 'final'")
                reply = "No pude completar la solicitud, intenta reformularla."
                append_message(db, conversation_id, "assistant", reply)
                yield StreamOutEvent(type="done", conversation_id=conversation_id, reply=reply)
                return

            if response.input_tokens or response.output_tokens:
                record_usage(
                    db,
                    model=get_settings().anthropic_model,
                    input_tokens=response.input_tokens,
                    output_tokens=response.output_tokens,
                )

            if not response.wants_tool_call:
                reply = "".join(accumulated_text)
                append_message(db, conversation_id, "assistant", reply)
                yield StreamOutEvent(type="done", conversation_id=conversation_id, reply=reply)
                return

            calls = response.tool_calls
            messages.append(AIMessage(role="assistant", content=response.text or "", tool_calls=calls))

            resolved, missing_tool_messages, pending_confirmation = self._evaluate_tool_calls(
                calls, conversation_id
            )

            if pending_confirmation is not None:
                yield StreamOutEvent(
                    type="confirmation",
                    conversation_id=conversation_id,
                    confirmation_id=pending_confirmation.pending.id,
                    confirmation_description=pending_confirmation.pending.description,
                )
                return

            for tool, call in self._execute_resolved_calls(resolved, missing_tool_messages, messages, db):
                yield StreamOutEvent(
                    type="tool_call",
                    tool_name=tool.name,
                    tool_description=tool.human_description(call.arguments),
                )

        logger.warning("Se alcanzó MAX_TOOL_ITERATIONS sin respuesta final del modelo (streaming).")
        reply = "No pude completar la solicitud, intenta reformularla."
        append_message(db, conversation_id, "assistant", reply)
        yield StreamOutEvent(type="done", conversation_id=conversation_id, reply=reply)

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
