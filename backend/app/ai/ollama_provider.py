"""Proveedor local Ollama para el modo local-first de ATLAS."""
from __future__ import annotations

import json
import uuid
from collections.abc import Iterator
from typing import Any

import requests

from app.ai.base import AIMessage, AIProvider, AIResponse, ToolCall, ToolSchema


class OllamaProvider(AIProvider):
    """Cliente de la API local de Ollama, incluyendo llamadas a herramientas."""

    def __init__(self, model: str, base_url: str = "http://127.0.0.1:11434", timeout: float = 120.0) -> None:
        if not model:
            raise ValueError("OLLAMA_MODEL está vacío. Elegí un modelo local, por ejemplo qwen3:4b.")
        self._model = model
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout

    @staticmethod
    def _tools(tools: list[ToolSchema]) -> list[dict[str, Any]]:
        return [
            {"type": "function", "function": {"name": tool.name, "description": tool.description, "parameters": tool.parameters}}
            for tool in tools
        ]

    @staticmethod
    def _messages(messages: list[AIMessage]) -> list[dict[str, Any]]:
        result: list[dict[str, Any]] = []
        for message in messages:
            item: dict[str, Any] = {"role": message.role, "content": message.content}
            if message.role == "tool" and message.name:
                item["tool_name"] = message.name
            if message.role == "assistant" and message.tool_calls:
                item["tool_calls"] = [
                    {"function": {"name": call.name, "arguments": call.arguments}}
                    for call in message.tool_calls
                ]
            result.append(item)
        return result

    def _payload(self, messages: list[AIMessage], tools: list[ToolSchema] | None, stream: bool) -> dict[str, Any]:
        payload: dict[str, Any] = {"model": self._model, "messages": self._messages(messages), "stream": stream}
        if tools:
            payload["tools"] = self._tools(tools)
        return payload

    def _unreachable(self) -> RuntimeError:
        return RuntimeError(
            f"No pude conectar con Ollama en {self._base_url}. Iniciá Ollama y descargá el modelo '{self._model}'."
        )

    @staticmethod
    def _calls(raw_calls: list[dict[str, Any]]) -> list[ToolCall]:
        calls = []
        for index, raw_call in enumerate(raw_calls):
            function = raw_call.get("function", {})
            name = function.get("name")
            if name:
                calls.append(
                    ToolCall(
                        id=f"ollama-{index}-{uuid.uuid4().hex[:8]}",
                        name=name,
                        arguments=function.get("arguments") or {},
                    )
                )
        return calls

    def chat(self, messages: list[AIMessage], tools: list[ToolSchema] | None = None) -> AIResponse:
        try:
            response = requests.post(
                f"{self._base_url}/api/chat", json=self._payload(messages, tools, stream=False), timeout=self._timeout
            )
            response.raise_for_status()
        except requests.RequestException as exc:
            raise self._unreachable() from exc

        message = response.json().get("message", {})
        return AIResponse(text=message.get("content") or None, tool_calls=self._calls(message.get("tool_calls") or []))

    def chat_stream(
        self, messages: list[AIMessage], tools: list[ToolSchema] | None = None
    ) -> Iterator[str | AIResponse]:
        # Con stream=True Ollama responde una línea JSON por fragmento; la última trae done=true.
        text_parts: list[str] = []
        raw_calls: list[dict[str, Any]] = []
        try:
            with requests.post(
                f"{self._base_url}/api/chat",
                json=self._payload(messages, tools, stream=True),
                timeout=self._timeout,
                stream=True,
            ) as response:
                response.raise_for_status()
                for line in response.iter_lines():
                    if not line:
                        continue
                    message = json.loads(line).get("message") or {}
                    raw_calls.extend(message.get("tool_calls") or [])
                    if message.get("content"):
                        text_parts.append(message["content"])
                        yield message["content"]
        except requests.RequestException as exc:
            raise self._unreachable() from exc
        yield AIResponse(text="".join(text_parts) or None, tool_calls=self._calls(raw_calls))
