from __future__ import annotations

from app.ai.base import AIMessage, AIProvider, AIResponse, ToolCall, ToolSchema
from app.core.orchestrator import Orchestrator
from app.events.bus import EventBus
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
    # Mensaje corto en español (se lee en voz alta): sin el JSON del proveedor.
    assert "sin crédito" in result.reply and "credit balance" not in result.reply


def test_friendly_ai_errors():
    from app.core.orchestrator import friendly_ai_error

    assert "clave" in friendly_ai_error(RuntimeError("Error code: 401 - invalid x-api-key"))
    assert "saturada" in friendly_ai_error(RuntimeError("Error code: 529 - overloaded_error"))
    assert "internet" in friendly_ai_error(ConnectionError("Connection error."))
    assert friendly_ai_error(ValueError("algo raro")).startswith("No pude conectar con la IA")


class _ScriptedProvider(AIProvider):
    """Devuelve respuestas prefijadas, una por llamada, y guarda lo que recibió."""

    def __init__(self, responses: list[AIResponse]) -> None:
        self._responses = list(responses)
        self.seen: list[list[AIMessage]] = []

    def chat(self, messages: list[AIMessage], tools: list[ToolSchema] | None = None) -> AIResponse:
        self.seen.append(list(messages))
        return self._responses.pop(0)


def _orchestrator(provider: AIProvider) -> Orchestrator:
    return Orchestrator(
        ai_provider=provider,
        registry=build_default_registry(),
        permissions=PermissionManager(),
        events=EventBus(),
    )


def test_all_tool_calls_of_one_turn_are_executed(db_session):
    provider = _ScriptedProvider(
        [
            AIResponse(
                tool_calls=[
                    ToolCall(id="a", name="get_current_time", arguments={}),
                    ToolCall(id="b", name="get_system_info", arguments={}),
                ]
            ),
            AIResponse(text="Son las 10 y la PC va bien."),
        ]
    )

    result = _orchestrator(provider).handle_message(db_session, "hora y estado")

    assert result.reply == "Son las 10 y la PC va bien."
    tool_messages = [m for m in provider.seen[1] if m.role == "tool"]
    assert [m.tool_call_id for m in tool_messages] == ["a", "b"]
    assert "cpu_percent" in tool_messages[1].content
    # El turno del modelo conserva las dos llamadas, antes de sus resultados.
    assistant = next(m for m in provider.seen[1] if m.role == "assistant" and m.tool_calls)
    assert [c.id for c in assistant.tool_calls] == ["a", "b"]


def test_confirmation_stops_the_rest_of_the_turn(db_session):
    provider = _ScriptedProvider(
        [
            AIResponse(
                tool_calls=[
                    ToolCall(id="a", name="get_current_time", arguments={}),
                    ToolCall(id="b", name="open_application", arguments={"application_name": "notepad"}),
                    ToolCall(id="c", name="get_system_info", arguments={}),
                ]
            ),
        ]
    )

    result = _orchestrator(provider).handle_message(db_session, "hora, abrí notepad y estado")

    assert result.requires_confirmation
    assert result.reply is None
    assert len(provider.seen) == 1  # no volvió al modelo: espera al usuario


def test_stream_message_emits_deltas_tools_and_done(db_session):
    provider = _ScriptedProvider(
        [
            AIResponse(tool_calls=[ToolCall(id="a", name="get_current_time", arguments={})]),
            AIResponse(text="Son las 10."),
        ]
    )

    events = list(_orchestrator(provider).stream_message(db_session, "hora"))

    assert [e.type for e in events] == ["start", "tool", "delta", "done"]
    assert events[1].name == "get_current_time"
    assert events[2].text == "Son las 10."
    assert events[3].result.reply == "Son las 10."
    assert events[3].result.conversation_id == events[0].conversation_id
