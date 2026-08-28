from __future__ import annotations

from types import SimpleNamespace

from app.ai.base import AIMessage, AIProvider, AIResponse, StreamEvent, ToolCall, ToolSchema
from app.core.orchestrator import CHARS_PER_TOKEN_ESTIMATE, Orchestrator, _trim_history_to_token_budget
from app.events.bus import EventBus
from app.security.audit import list_recent
from app.security.permissions import PermissionManager
from app.tools.registry import build_default_registry


class _BrokenProvider(AIProvider):
    """Simula una falla del proveedor de IA (red, billing, etc.)."""

    def chat(self, messages: list[AIMessage], tools: list[ToolSchema] | None = None) -> AIResponse:
        raise RuntimeError("Your credit balance is too low to access the Anthropic API.")


def test_ai_provider_failure_returns_friendly_message_instead_of_crashing(db_session):
    orchestrator = Orchestrator(
        ai_provider=_BrokenProvider(),
        registry=build_default_registry(),
        permissions=PermissionManager(),
        events=EventBus(),
    )
    result = orchestrator.handle_message(db_session, "hola")
    assert result.reply is not None
    assert "No pude conectar con la IA" in result.reply
    assert not result.requires_confirmation


def _msg(content: str):
    return SimpleNamespace(content=content)


def test_trim_history_keeps_everything_under_budget():
    history = [_msg("hola"), _msg("¿qué hora es?"), _msg("son las 10")]
    trimmed = _trim_history_to_token_budget(history, budget_tokens=1000)
    assert trimmed == history


def test_trim_history_drops_oldest_messages_first():
    # Cada mensaje "grande" ocupa casi todo el presupuesto (100 tokens) —
    # con 2 de esos ya no entra un tercero, así que se debe quedar solo con
    # los dos más recientes, no los dos más viejos.
    big = "x" * (100 * CHARS_PER_TOKEN_ESTIMATE)
    history = [_msg("viejo:" + big), _msg("medio:" + big), _msg("nuevo:" + big)]
    trimmed = _trim_history_to_token_budget(history, budget_tokens=250)
    assert [m.content for m in trimmed] == [history[1].content, history[2].content]


def test_trim_history_always_keeps_at_least_the_last_message():
    # Un solo mensaje que por sí solo ya excede el presupuesto: se conserva
    # igual — cortarlo dejaría a ATLAS sin ver el turno actual del usuario.
    huge = "x" * (10_000 * CHARS_PER_TOKEN_ESTIMATE)
    history = [_msg("previo"), _msg(huge)]
    trimmed = _trim_history_to_token_budget(history, budget_tokens=10)
    assert trimmed == [history[1]]


def test_trim_history_handles_empty_list():
    assert _trim_history_to_token_budget([], budget_tokens=1000) == []


class _TwoReadOnlyCallsProvider(AIProvider):
    """Simula al modelo pidiendo dos tools READ_ONLY en un mismo turno."""

    def chat(self, messages: list[AIMessage], tools: list[ToolSchema] | None = None) -> AIResponse:
        if messages and messages[-1].role == "tool":
            return AIResponse(text="Listo, resolví ambas.")
        return AIResponse(
            tool_calls=[
                ToolCall(id="call-1", name="get_current_time", arguments={}),
                ToolCall(id="call-2", name="get_system_info", arguments={}),
            ]
        )


def test_resolves_multiple_tool_calls_in_the_same_turn(db_session):
    orchestrator = Orchestrator(
        ai_provider=_TwoReadOnlyCallsProvider(),
        registry=build_default_registry(),
        permissions=PermissionManager(),
        events=EventBus(),
    )
    result = orchestrator.handle_message(db_session, "dime la hora y el estado del sistema")

    assert result.reply == "Listo, resolví ambas."
    assert not result.requires_confirmation

    recent = list_recent(db_session, limit=10)
    tool_names = {entry.tool_name for entry in recent}
    assert tool_names == {"get_current_time", "get_system_info"}


class _MixedRiskCallsProvider(AIProvider):
    """Un turno con una tool READ_ONLY y una que exige confirmación
    (open_application es MEDIUM_RISK) — ninguna de las dos debe ejecutarse
    hasta que el usuario confirme."""

    def chat(self, messages: list[AIMessage], tools: list[ToolSchema] | None = None) -> AIResponse:
        return AIResponse(
            tool_calls=[
                ToolCall(id="call-1", name="get_current_time", arguments={}),
                ToolCall(id="call-2", name="open_application", arguments={"application_name": "notepad"}),
            ]
        )


def test_a_call_needing_confirmation_blocks_the_whole_batch(db_session):
    orchestrator = Orchestrator(
        ai_provider=_MixedRiskCallsProvider(),
        registry=build_default_registry(),
        permissions=PermissionManager(),
        events=EventBus(),
    )
    result = orchestrator.handle_message(db_session, "dime la hora y abre notepad")

    assert result.requires_confirmation
    assert result.confirmation_id is not None
    # Ninguna de las dos tools del lote se ejecutó todavía — ni siquiera la
    # que por sí sola no necesitaba confirmación.
    assert list_recent(db_session, limit=10) == []


class _StreamingTextProvider(AIProvider):
    """Simula un modelo que responde directo en texto (sin tools), emitido
    en varios deltas — como haría AnthropicProvider.chat_stream real."""

    def chat(self, messages: list[AIMessage], tools: list[ToolSchema] | None = None) -> AIResponse:
        raise AssertionError("no debería llamarse chat() sin streaming en este test")

    def chat_stream(self, messages: list[AIMessage], tools: list[ToolSchema] | None = None):
        for piece in ["Hola", ", ", "¿en qué te ayudo?"]:
            yield StreamEvent(type="delta", text=piece)
        yield StreamEvent(
            type="final",
            response=AIResponse(text="Hola, ¿en qué te ayudo?", input_tokens=3, output_tokens=5),
        )


def test_handle_message_stream_yields_deltas_then_done(db_session):
    orchestrator = Orchestrator(
        ai_provider=_StreamingTextProvider(),
        registry=build_default_registry(),
        permissions=PermissionManager(),
        events=EventBus(),
    )
    events = list(orchestrator.handle_message_stream(db_session, "hola"))

    token_events = [e for e in events if e.type == "token"]
    assert [e.text for e in token_events] == ["Hola", ", ", "¿en qué te ayudo?"]

    assert events[-1].type == "done"
    assert events[-1].reply == "Hola, ¿en qué te ayudo?"
    assert events[-1].conversation_id


class _StreamingToolCallProvider(AIProvider):
    """Primer turno: pide una tool READ_ONLY, emitiendo un poco de texto de
    preámbulo primero (como "Reviso la hora..."). Segundo turno: responde en
    texto una vez que ve el tool_result."""

    def chat(self, messages, tools=None):
        raise AssertionError("no debería llamarse chat() sin streaming en este test")

    def chat_stream(self, messages, tools=None):
        if messages and messages[-1].role == "tool":
            for piece in ["Son ", "las 10."]:
                yield StreamEvent(type="delta", text=piece)
            yield StreamEvent(type="final", response=AIResponse(text="Son las 10."))
            return

        yield StreamEvent(type="delta", text="Reviso la hora...")
        yield StreamEvent(
            type="final",
            response=AIResponse(
                text="Reviso la hora...",
                tool_calls=[ToolCall(id="call-1", name="get_current_time", arguments={})],
            ),
        )


def test_handle_message_stream_emits_tool_call_event_and_full_text(db_session):
    orchestrator = Orchestrator(
        ai_provider=_StreamingToolCallProvider(),
        registry=build_default_registry(),
        permissions=PermissionManager(),
        events=EventBus(),
    )
    events = list(orchestrator.handle_message_stream(db_session, "¿qué hora es?"))

    tool_call_events = [e for e in events if e.type == "tool_call"]
    assert len(tool_call_events) == 1
    assert tool_call_events[0].tool_name == "get_current_time"

    done = events[-1]
    assert done.type == "done"
    # El preámbulo del primer turno ("Reviso la hora...") y la respuesta
    # final del segundo ("Son las 10.") quedan concatenados: ambos ya se le
    # mostraron al usuario en vivo, así que no se puede descartar ninguno.
    assert done.reply == "Reviso la hora...Son las 10."


class _StreamingConfirmationProvider(AIProvider):
    """Pide una tool que exige confirmación (open_application, MEDIUM_RISK)."""

    def chat(self, messages, tools=None):
        raise AssertionError("no debería llamarse chat() sin streaming en este test")

    def chat_stream(self, messages, tools=None):
        yield StreamEvent(
            type="final",
            response=AIResponse(
                tool_calls=[
                    ToolCall(id="call-1", name="open_application", arguments={"application_name": "notepad"})
                ]
            ),
        )


def test_handle_message_stream_emits_confirmation_event(db_session):
    orchestrator = Orchestrator(
        ai_provider=_StreamingConfirmationProvider(),
        registry=build_default_registry(),
        permissions=PermissionManager(),
        events=EventBus(),
    )
    events = list(orchestrator.handle_message_stream(db_session, "abre notepad"))

    assert events[-1].type == "confirmation"
    assert events[-1].confirmation_id is not None
    assert list_recent(db_session, limit=10) == []
