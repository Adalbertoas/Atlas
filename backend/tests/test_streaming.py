"""Chat en streaming, turnos con varias tools por el mock, y tareas en segundo plano."""
from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace

import requests

from app.ai.anthropic_provider import AnthropicProvider
from app.ai.base import AIMessage, AIResponse, ToolSchema
from app.ai.mock_provider import MockProvider
from app.ai.ollama_provider import OllamaProvider
from app.core.background import BackgroundJobs

USER = [AIMessage(role="user", content="hola")]


def _events(response) -> list[dict]:
    return [json.loads(line[len("data: "):]) for line in response.text.splitlines() if line.startswith("data: ")]


# ---------- endpoint ----------


def test_chat_stream_endpoint_emits_events_in_order(client, auth_headers):
    response = client.post("/api/v1/chat/stream", json={"message": "¿qué hora es?"}, headers=auth_headers)

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    events = _events(response)
    assert [e["type"] for e in events] == ["start", "tool", "tool_done", "delta", "done"]
    assert events[1]["name"] == "get_current_time"
    assert events[2] == {"type": "tool_done", "name": "get_current_time", "success": True}
    done = events[-1]
    assert done["reply"].startswith("Listo. Resultado de get_current_time")
    assert done["reply"] == events[3]["text"]
    assert done["conversation_id"] == events[0]["conversation_id"]
    assert done["requires_confirmation"] is False


def test_chat_stream_endpoint_reports_pending_confirmation(client, auth_headers):
    events = _events(client.post("/api/v1/chat/stream", json={"message": "abre notepad"}, headers=auth_headers))

    assert [e["type"] for e in events] == ["start", "done"]
    assert events[-1]["requires_confirmation"] is True
    assert events[-1]["confirmation_id"]


def test_chat_stream_endpoint_requires_login(client):
    assert client.post("/api/v1/chat/stream", json={"message": "hola"}).status_code in (401, 403)


def test_one_message_with_two_requests_runs_two_tools(client, auth_headers):
    body = client.post(
        "/api/v1/chat", json={"message": "¿qué hora es? y además decime el estado del sistema"}, headers=auth_headers
    ).json()

    assert "Resultado de get_current_time" in body["reply"]
    assert "Resultado de get_system_info" in body["reply"]
    assert "cpu_percent" in body["reply"]


# ---------- mock ----------


def _plan(message: str, *tools: str) -> list[tuple[str, dict]]:
    schemas = [ToolSchema(name=name, description="", parameters={}) for name in tools]
    response = MockProvider().chat([AIMessage(role="user", content=message)], tools=schemas)
    return [(call.name, call.arguments) for call in response.tool_calls]


def test_mock_understands_the_new_requests():
    assert _plan("avisame si hay un terremoto mayor a 5 cerca de Chile", "create_world_alert", "query_world") == [
        ("create_world_alert", {"topic": "earthquakes", "place": "Chile", "min_magnitude": 5.0})
    ]
    assert _plan("avisame cuando pase la ISS sobre Rosario", "create_world_alert") == [
        ("create_world_alert", {"topic": "satellite_pass", "place": "Rosario"})
    ]
    assert _plan("seguí el vuelo ARG1676", "show_world_view") == [
        ("show_world_view", {"follow_aircraft": "ARG1676"})
    ]
    assert _plan("seguí la ISS", "show_world_view") == [("show_world_view", {"follow_satellite": "ISS"})]
    assert _plan("marcame la ruta de Buenos Aires a Córdoba", "show_world_view") == [
        ("show_world_view", {"marks": [{"type": "route", "places": ["Buenos Aires", "Córdoba"], "label": "Ruta"}]})
    ]
    assert _plan("recordame llamar al médico a las 9", "create_reminder") == [
        ("create_reminder", {"message": "llamar al médico", "at": "09:00"})
    ]
    assert _plan("recordame el té en 30 segundos", "create_reminder") == [
        ("create_reminder", {"message": "el té", "in_minutes": 0.5})
    ]
    assert _plan("buscá en internet el clima en Marte", "web_search", "query_world") == [
        ("web_search", {"query": "el clima en Marte"})
    ]
    assert _plan("buscá garantía en mis documentos", "search_documents") == [
        ("search_documents", {"query": "garantía"})
    ]
    assert _plan("resumime lo que copié", "read_clipboard") == [("read_clipboard", {})]
    assert _plan("poné esta ventana a la izquierda", "manage_window") == [("manage_window", {"action": "left"})]
    assert _plan("qué clima hace en Lima", "query_world") == [("query_world", {"topic": "weather", "place": "Lima"})]
    assert _plan("dame el briefing", "daily_briefing") == [("daily_briefing", {})]


def test_mock_ignores_tools_that_are_not_available():
    assert _plan("seguí la ISS") == []
    assert _plan("buscá en internet algo") == []


# ---------- proveedores ----------


def test_default_chat_stream_wraps_a_plain_chat():
    chunks = list(MockProvider().chat_stream(USER, tools=[]))
    assert isinstance(chunks[0], str)
    assert isinstance(chunks[-1], AIResponse)
    assert chunks[-1].text == chunks[0]


def test_ollama_stream_yields_text_as_it_arrives(monkeypatch):
    lines = [
        {"message": {"content": "Hola"}},
        {"message": {"content": ", ¿qué tal?"}},
        {"message": {"content": ""}, "done": True},
    ]

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *args) -> None:
            pass

        def raise_for_status(self) -> None:
            pass

        def iter_lines(self):
            return [json.dumps(line).encode() for line in lines] + [b""]

    sent = {}

    def fake_post(url, json, timeout, stream):  # noqa: A002 — nombre del parámetro de requests
        sent.update(json)
        return Response()

    monkeypatch.setattr(requests, "post", fake_post)

    chunks = list(OllamaProvider(model="qwen3:4b").chat_stream(USER))

    assert sent["stream"] is True
    assert chunks[:2] == ["Hola", ", ¿qué tal?"]
    assert chunks[-1].text == "Hola, ¿qué tal?"
    assert chunks[-1].tool_calls == []


def test_ollama_stream_collects_tool_calls(monkeypatch):
    call = {"function": {"name": "get_current_time", "arguments": {}}}

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *args) -> None:
            pass

        def raise_for_status(self) -> None:
            pass

        def iter_lines(self):
            return [json.dumps({"message": {"content": "", "tool_calls": [call]}, "done": True}).encode()]

    monkeypatch.setattr(requests, "post", lambda *a, **k: Response())

    (final,) = list(OllamaProvider(model="qwen3:4b").chat_stream(USER))

    assert final.text is None
    assert [c.name for c in final.tool_calls] == ["get_current_time"]


def test_ollama_stream_explains_when_ollama_is_down(monkeypatch):
    def refuse(*args, **kwargs):
        raise requests.ConnectionError("refused")

    monkeypatch.setattr(requests, "post", refuse)

    try:
        list(OllamaProvider(model="qwen3:4b").chat_stream(USER))
    except RuntimeError as exc:
        assert "No pude conectar con Ollama" in str(exc)
    else:
        raise AssertionError("se esperaba RuntimeError")


def test_anthropic_stream_yields_text_then_the_full_response():
    final = SimpleNamespace(
        content=[
            SimpleNamespace(type="text", text="Reviso la hora."),
            SimpleNamespace(type="tool_use", id="tu_1", name="get_current_time", input={}),
        ]
    )

    class Stream:
        text_stream = ["Reviso ", "la hora."]

        def __enter__(self):
            return self

        def __exit__(self, *args) -> None:
            pass

        def get_final_message(self):
            return final

    requested = {}

    def fake_stream(**kwargs):
        requested.update(kwargs)
        return Stream()

    provider = AnthropicProvider(api_key="test", model="claude-test")
    provider._client = SimpleNamespace(messages=SimpleNamespace(stream=fake_stream))

    chunks = list(provider.chat_stream([AIMessage(role="system", content="Sos ATLAS."), *USER]))

    assert chunks[:2] == ["Reviso ", "la hora."]
    assert chunks[-1].text == "Reviso la hora."
    assert [(c.id, c.name) for c in chunks[-1].tool_calls] == [("tu_1", "get_current_time")]
    assert requested["system"] == "Sos ATLAS."
    assert requested["messages"] == [{"role": "user", "content": "hola"}]


def test_anthropic_groups_results_of_one_turn_in_a_single_message():
    from app.ai.base import ToolCall

    provider = AnthropicProvider(api_key="test", model="claude-test")
    calls = [ToolCall(id="a", name="get_current_time", arguments={}), ToolCall(id="b", name="get_system_info", arguments={})]
    messages = [
        *USER,
        AIMessage(role="assistant", content="", tool_calls=calls),
        AIMessage(role="tool", content="10:00", tool_call_id="a", name="get_current_time"),
        AIMessage(role="tool", content="cpu 5%", tool_call_id="b", name="get_system_info"),
    ]

    sent = provider._request(messages, None)["messages"]

    assert [m["role"] for m in sent] == ["user", "assistant", "user"]
    assert [block["tool_use_id"] for block in sent[2]["content"]] == ["a", "b"]


# ---------- tareas en segundo plano ----------


def test_background_jobs_run_repeatedly_and_survive_a_failing_job():
    async def scenario() -> tuple[int, int]:
        counts = {"ok": 0, "broken": 0}

        def ok() -> None:
            counts["ok"] += 1

        def broken() -> None:
            counts["broken"] += 1
            raise RuntimeError("falla a propósito")

        jobs = BackgroundJobs()
        jobs.add("ok", 0.02, ok)
        jobs.add("rota", 0.02, broken)
        jobs.start()
        await asyncio.sleep(0.25)
        await jobs.stop()
        stopped_at = counts["ok"]
        await asyncio.sleep(0.1)
        assert counts["ok"] == stopped_at  # stop() las detiene de verdad
        return counts["ok"], counts["broken"]

    ok_runs, broken_runs = asyncio.run(scenario())
    assert ok_runs >= 2
    assert broken_runs >= 2  # una tarea que falla se sigue reintentando
