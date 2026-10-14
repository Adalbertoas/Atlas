"""Implementación de AIProvider usando la API de Anthropic (Claude).

La api_key se pasa explícitamente al constructor (no se lee de os.environ
aquí dentro). Esto es intencional: prepara el camino a que, en una futura
versión multi-usuario (BYOK — sección de contexto del plan), cada usuario
aporte su propia key sin cambiar esta clase.
"""
from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import anthropic

from app.ai.base import AIMessage, AIProvider, AIResponse, ToolCall, ToolSchema

_ROLE_MAP = {"user": "user", "assistant": "assistant"}


class AnthropicProvider(AIProvider):
    def __init__(self, api_key: str, model: str, max_tokens: int = 1024) -> None:
        if not api_key:
            raise ValueError(
                "ANTHROPIC_API_KEY vacío. Configura tu key en .env o usa AI_PROVIDER=mock."
            )
        self._client = anthropic.Anthropic(api_key=api_key)
        self._model = model
        self._max_tokens = max_tokens

    def _to_anthropic_tools(self, tools: list[ToolSchema]) -> list[dict[str, Any]]:
        return [
            {
                "name": t.name,
                "description": t.description,
                "input_schema": t.parameters,
            }
            for t in tools
        ]

    def _request(self, messages: list[AIMessage], tools: list[ToolSchema] | None) -> dict[str, Any]:
        """Argumentos de la llamada a la API, compartidos por chat() y chat_stream()."""
        system_prompt = "\n".join(m.content for m in messages if m.role == "system")

        anthropic_messages: list[dict[str, Any]] = []
        for m in messages:
            if m.role == "system":
                continue
            if m.role == "tool":
                block = {"type": "tool_result", "tool_use_id": m.tool_call_id, "content": m.content}
                previous = anthropic_messages[-1] if anthropic_messages else None
                # Los resultados de varias tools pedidas en un mismo turno van
                # juntos en un único mensaje "user", que es lo que espera la API.
                if (
                    previous
                    and previous["role"] == "user"
                    and isinstance(previous["content"], list)
                    and previous["content"]
                    and previous["content"][0].get("type") == "tool_result"
                ):
                    previous["content"].append(block)
                else:
                    anthropic_messages.append({"role": "user", "content": [block]})
            elif m.role == "assistant" and m.tool_calls:
                # El turno del modelo que pidió la(s) tool(s): hay que reenviar
                # el bloque tool_use tal cual, si no la API rechaza el
                # tool_result que le sigue.
                content: list[dict[str, Any]] = []
                if m.content:
                    content.append({"type": "text", "text": m.content})
                for call in m.tool_calls:
                    content.append(
                        {"type": "tool_use", "id": call.id, "name": call.name, "input": call.arguments}
                    )
                anthropic_messages.append({"role": "assistant", "content": content})
            else:
                anthropic_messages.append({"role": _ROLE_MAP[m.role], "content": m.content})

        kwargs: dict[str, Any] = dict(
            model=self._model,
            max_tokens=self._max_tokens,
            system=system_prompt or None,
            messages=anthropic_messages,
        )
        if tools:
            kwargs["tools"] = self._to_anthropic_tools(tools)

        return kwargs

    @staticmethod
    def _to_response(message: Any) -> AIResponse:
        text_parts: list[str] = []
        tool_calls: list[ToolCall] = []
        for block in message.content:
            if block.type == "text":
                text_parts.append(block.text)
            elif block.type == "tool_use":
                tool_calls.append(ToolCall(id=block.id, name=block.name, arguments=block.input))
        return AIResponse(text="\n".join(text_parts) or None, tool_calls=tool_calls)

    def chat(
        self,
        messages: list[AIMessage],
        tools: list[ToolSchema] | None = None,
    ) -> AIResponse:
        return self._to_response(self._client.messages.create(**self._request(messages, tools)))

    def chat_stream(
        self,
        messages: list[AIMessage],
        tools: list[ToolSchema] | None = None,
    ) -> Iterator[str | AIResponse]:
        with self._client.messages.stream(**self._request(messages, tools)) as stream:
            yield from stream.text_stream
            yield self._to_response(stream.get_final_message())
