"""AIProvider: interfaz abstracta de IA de ATLAS (sección 3 del prompt maestro).

Ningún otro módulo debe importar un SDK de IA directamente (ej. `anthropic`,
`openai`) — todo pasa por esta interfaz. Así ATLAS puede cambiar de proveedor,
o soportar una key por usuario (BYOK), sin tocar el Orchestrator ni las tools.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Iterator
from dataclasses import dataclass, field
from typing import Any, Literal


@dataclass
class ToolSchema:
    """Descripción de una tool en un formato agnóstico de proveedor."""

    name: str
    description: str
    parameters: dict[str, Any]  # JSON Schema


@dataclass
class ToolCall:
    id: str
    name: str
    arguments: dict[str, Any]


@dataclass
class AIMessage:
    role: Literal["system", "user", "assistant", "tool"]
    content: str
    tool_call_id: str | None = None  # solo para role="tool"
    name: str | None = None  # solo para role="tool"
    # Para role="assistant": tool_calls que el modelo pidió ejecutar en este
    # turno. Debe reenviarse al proveedor junto con el/los tool_result
    # correspondientes — varios proveedores (Anthropic incluido) exigen que
    # el bloque tool_use quede en el historial antes de aceptar su resultado.
    tool_calls: list[ToolCall] = field(default_factory=list)


@dataclass
class AIResponse:
    """Resultado de una llamada a chat(): o bien texto final, o tool_calls a resolver."""

    text: str | None = None
    tool_calls: list[ToolCall] = field(default_factory=list)
    # Tokens consumidos por esta llamada (Fase 28: límite de gasto). 0 en
    # MockProvider — no hay nada que medir sin pegarle a una API real.
    input_tokens: int = 0
    output_tokens: int = 0

    @property
    def wants_tool_call(self) -> bool:
        return len(self.tool_calls) > 0


@dataclass
class StreamEvent:
    """Un fragmento de la respuesta en streaming (ver AIProvider.chat_stream).

    "delta": texto parcial a mostrar apenas llega (`text`).
    "final": la respuesta completa una vez que el modelo terminó — mismo
    objeto que devolvería chat() sin streaming (`response`), con
    tool_calls/tokens ya resueltos. Siempre es el último evento emitido.
    """

    type: Literal["delta", "final"]
    text: str | None = None
    response: AIResponse | None = None


class AIProvider(ABC):
    """Interfaz que debe implementar cualquier proveedor de IA de ATLAS."""

    @abstractmethod
    def chat(
        self,
        messages: list[AIMessage],
        tools: list[ToolSchema] | None = None,
    ) -> AIResponse:
        """Envía la conversación al modelo y devuelve texto o tool_calls a ejecutar."""
        raise NotImplementedError

    def chat_stream(
        self,
        messages: list[AIMessage],
        tools: list[ToolSchema] | None = None,
    ) -> Iterator[StreamEvent]:
        """Como chat(), pero entregando el texto a medida que se genera.

        Implementación por defecto, no abstracta a propósito: un provider
        que no sepa transmitir token a token (MockProvider, o uno nuevo que
        se agregue sin pensar en streaming) sigue funcionando solo con
        chat() — entrega la respuesta completa como un único "delta" en vez
        de romper. AnthropicProvider la sobreescribe con streaming real.
        """
        response = self.chat(messages, tools=tools)
        if response.text:
            yield StreamEvent(type="delta", text=response.text)
        yield StreamEvent(type="final", response=response)
