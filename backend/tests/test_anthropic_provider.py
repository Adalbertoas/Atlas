from __future__ import annotations

from types import SimpleNamespace

from app.ai.anthropic_provider import AnthropicProvider
from app.ai.base import AIMessage, ToolCall


class _FakeMessages:
    """Sustituye a client.messages para capturar el payload armado sin
    pegarle a la red real, y devolver una respuesta de texto simple."""

    def __init__(self) -> None:
        self.last_kwargs: dict | None = None

    def create(self, **kwargs):
        self.last_kwargs = kwargs
        return SimpleNamespace(
            content=[SimpleNamespace(type="text", text="ok")],
            usage=SimpleNamespace(input_tokens=1, output_tokens=1),
        )


def _provider_with_fake_client() -> tuple[AnthropicProvider, _FakeMessages]:
    provider = AnthropicProvider(api_key="test-key", model="claude-test")
    fake_messages = _FakeMessages()
    provider._client = SimpleNamespace(messages=fake_messages)
    return provider, fake_messages


def test_multiple_tool_results_merge_into_one_user_turn():
    """Anthropic exige que todos los tool_result de un mismo turno del
    modelo viajen juntos en un único mensaje "user" — dos AIMessages "tool"
    consecutivos (el Orchestrator resolviendo varios tool_calls de un mismo
    turno) no deben volverse dos turnos "user" separados."""
    provider, fake_messages = _provider_with_fake_client()

    messages = [
        AIMessage(role="system", content="system prompt"),
        AIMessage(role="user", content="dime la hora y el estado del sistema"),
        AIMessage(
            role="assistant",
            content="",
            tool_calls=[
                ToolCall(id="call-1", name="get_current_time", arguments={}),
                ToolCall(id="call-2", name="get_system_info", arguments={}),
            ],
        ),
        AIMessage(role="tool", content="son las 10", tool_call_id="call-1", name="get_current_time"),
        AIMessage(role="tool", content="cpu 10%", tool_call_id="call-2", name="get_system_info"),
    ]

    provider.chat(messages, tools=[])

    sent = fake_messages.last_kwargs["messages"]
    # user, assistant(tool_use x2), user(tool_result x2) — no dos turnos "user" separados.
    roles = [m["role"] for m in sent]
    assert roles == ["user", "assistant", "user"]

    tool_result_turn = sent[-1]
    assert isinstance(tool_result_turn["content"], list)
    assert len(tool_result_turn["content"]) == 2
    assert {block["tool_use_id"] for block in tool_result_turn["content"]} == {"call-1", "call-2"}


class _FakeStreamContext:
    """Sustituye al context manager que devuelve client.messages.stream():
    `text_stream` entrega los deltas de texto, get_final_message() el
    Message completo ya ensamblado — misma forma que la respuesta de
    messages.create()."""

    def __init__(self, deltas: list[str], final_message) -> None:
        self._deltas = deltas
        self._final_message = final_message

    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        return False

    @property
    def text_stream(self):
        yield from self._deltas

    def get_final_message(self):
        return self._final_message


class _FakeStreamingMessages:
    def __init__(self, deltas: list[str], final_message) -> None:
        self._deltas = deltas
        self._final_message = final_message
        self.last_kwargs: dict | None = None

    def stream(self, **kwargs):
        self.last_kwargs = kwargs
        return _FakeStreamContext(self._deltas, self._final_message)


def test_chat_stream_yields_deltas_then_the_final_response():
    final_message = SimpleNamespace(
        content=[SimpleNamespace(type="text", text="Hola, ¿en qué te ayudo?")],
        usage=SimpleNamespace(input_tokens=5, output_tokens=7),
    )
    fake_messages = _FakeStreamingMessages(["Hola, ", "¿en qué ", "te ayudo?"], final_message)
    provider = AnthropicProvider(api_key="test-key", model="claude-test")
    provider._client = SimpleNamespace(messages=fake_messages)

    events = list(provider.chat_stream([AIMessage(role="user", content="hola")], tools=[]))

    deltas = [e for e in events if e.type == "delta"]
    assert [e.text for e in deltas] == ["Hola, ", "¿en qué ", "te ayudo?"]

    assert events[-1].type == "final"
    final_response = events[-1].response
    assert final_response.text == "Hola, ¿en qué te ayudo?"
    assert final_response.input_tokens == 5
    assert final_response.output_tokens == 7
    assert final_response.tool_calls == []


def test_chat_stream_final_response_includes_tool_calls():
    final_message = SimpleNamespace(
        content=[
            SimpleNamespace(type="text", text="Reviso el clima..."),
            SimpleNamespace(type="tool_use", id="call-1", name="get_weather", input={"city": "Bogotá"}),
        ],
        usage=SimpleNamespace(input_tokens=3, output_tokens=4),
    )
    fake_messages = _FakeStreamingMessages(["Reviso el clima..."], final_message)
    provider = AnthropicProvider(api_key="test-key", model="claude-test")
    provider._client = SimpleNamespace(messages=fake_messages)

    events = list(provider.chat_stream([AIMessage(role="user", content="clima en bogotá")], tools=[]))

    final_response = events[-1].response
    assert len(final_response.tool_calls) == 1
    assert final_response.tool_calls[0].name == "get_weather"


def test_assistant_turn_carries_both_tool_use_blocks():
    provider, fake_messages = _provider_with_fake_client()

    messages = [
        AIMessage(role="user", content="dime la hora y el estado del sistema"),
        AIMessage(
            role="assistant",
            content="",
            tool_calls=[
                ToolCall(id="call-1", name="get_current_time", arguments={}),
                ToolCall(id="call-2", name="get_system_info", arguments={}),
            ],
        ),
        AIMessage(role="tool", content="son las 10", tool_call_id="call-1", name="get_current_time"),
        AIMessage(role="tool", content="cpu 10%", tool_call_id="call-2", name="get_system_info"),
    ]

    provider.chat(messages, tools=[])

    sent = fake_messages.last_kwargs["messages"]
    assistant_turn = next(m for m in sent if m["role"] == "assistant")
    tool_use_blocks = [b for b in assistant_turn["content"] if b["type"] == "tool_use"]
    assert {b["id"] for b in tool_use_blocks} == {"call-1", "call-2"}
