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
class AIAttachment:
    """Imagen o PDF que el usuario adjuntó a su mensaje (ver app.core.attachments)."""

    kind: Literal["image", "pdf"]
    mime_type: str
    data: str  # base64
    name: str = ""
    # Vacío = el archivo tal cual. Si no, es un recorte ampliado de la imagen
    # `name` para leer letra chica, y dice cuál ("parte 1 de 3, de arriba hacia abajo").
    detail: str = ""


@dataclass
class AIMessage:
    role: Literal["system", "user", "assistant", "tool"]
    content: str
    tool_call_id: str | None = None  # solo para role="tool"
    name: str | None = None  # solo para role="tool"
    # Solo para role="user": archivos adjuntos que el modelo debe ver junto al texto.
    # Únicamente se envían si el proveedor tiene supports_attachments.
    attachments: list[AIAttachment] = field(default_factory=list)
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

    @property
    def wants_tool_call(self) -> bool:
        return len(self.tool_calls) > 0


class AIProvider(ABC):
    """Interfaz que debe implementar cualquier proveedor de IA de ATLAS."""

    # True si el modelo puede ver imágenes/PDF adjuntos directamente. Si no, el
    # Orchestrator se los describe en texto con el VisionProvider.
    supports_attachments: bool = False

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
    ) -> Iterator[str | AIResponse]:
        """Como chat(), pero entrega el texto a medida que el modelo lo genera:
        emite fragmentos (str) y, al final, siempre el AIResponse completo.

        Implementación por defecto para proveedores sin streaming: un único
        fragmento con todo el texto. Si el turno pide tools no se emite texto.
        """
        response = self.chat(messages, tools=tools)
        if response.text and not response.wants_tool_call:
            yield response.text
        yield response
