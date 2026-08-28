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

from app.ai.base import AIMessage, AIProvider, AIResponse, StreamEvent, ToolCall, ToolSchema

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

    def _build_kwargs(self, messages: list[AIMessage], tools: list[ToolSchema] | None) -> dict[str, Any]:
        """Arma el payload de la Messages API a partir de los AIMessage
        agnósticos de proveedor. Compartido por chat() y chat_stream() —
        antes de que existiera streaming esta lógica vivía inline dentro de
        chat(); separarla evita mantener dos copias que puedan divergir."""
        system_prompt = "\n".join(m.content for m in messages if m.role == "system")

        anthropic_messages: list[dict[str, Any]] = []
        for m in messages:
            if m.role == "system":
                continue
            if m.role == "tool":
                tool_result = {
                    "type": "tool_result",
                    "tool_use_id": m.tool_call_id,
                    "content": m.content,
                }
                # Cuando el Orchestrator resuelve varios tool_calls de un mismo
                # turno del modelo, llegan acá como AIMessages "tool"
                # consecutivos. Anthropic exige que todos sus tool_result
                # viajen juntos en un único turno "user" — dos turnos "user"
                # seguidos (uno por tool_result) violan la alternancia de
                # roles que la API exige y la rechaza. Se detecta el turno
                # anterior por su `content` en lista (los turnos "user" de
                # texto normal lo llevan como string).
                previous = anthropic_messages[-1] if anthropic_messages else None
                if previous is not None and previous["role"] == "user" and isinstance(previous["content"], list):
                    previous["content"].append(tool_result)
                else:
                    anthropic_messages.append({"role": "user", "content": [tool_result]})
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

    def _parse_response(self, response: Any) -> AIResponse:
        """Convierte un Message de Anthropic (de messages.create() o de
        stream.get_final_message() — misma forma) al AIResponse agnóstico."""
        text_parts: list[str] = []
        tool_calls: list[ToolCall] = []
        for block in response.content:
            if block.type == "text":
                text_parts.append(block.text)
            elif block.type == "tool_use":
                tool_calls.append(ToolCall(id=block.id, name=block.name, arguments=block.input))

        usage = response.usage
        return AIResponse(
            text="\n".join(text_parts) or None,
            tool_calls=tool_calls,
            input_tokens=usage.input_tokens if usage else 0,
            output_tokens=usage.output_tokens if usage else 0,
        )

    def chat(
        self,
        messages: list[AIMessage],
        tools: list[ToolSchema] | None = None,
    ) -> AIResponse:
        kwargs = self._build_kwargs(messages, tools)
        response = self._client.messages.create(**kwargs)
        return self._parse_response(response)

    def chat_stream(
        self,
        messages: list[AIMessage],
        tools: list[ToolSchema] | None = None,
    ) -> Iterator[StreamEvent]:
        """Streaming real vía el helper de alto nivel del SDK
        (`client.messages.stream()`): `text_stream` entrega el texto a
        medida que llega (nunca incluye tool_use, solo texto), y
        `get_final_message()` devuelve el Message completo y ya acumulado
        —incluidos los bloques tool_use, con su JSON parcial ya ensamblado
        por el propio SDK— así que no hace falta reimplementar ese
        ensamblado a mano acá."""
        kwargs = self._build_kwargs(messages, tools)
        with self._client.messages.stream(**kwargs) as stream:
            for text in stream.text_stream:
                yield StreamEvent(type="delta", text=text)
            final_message = stream.get_final_message()
        yield StreamEvent(type="final", response=self._parse_response(final_message))
