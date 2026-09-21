"""Enrutamiento de proveedores de IA sin acoplar el Orchestrator a uno solo."""
from __future__ import annotations

from app.ai.base import AIMessage, AIProvider, AIResponse, StreamEvent, ToolSchema


class AIRouter(AIProvider):
    def __init__(self, providers: dict[str, AIProvider], default_provider: str) -> None:
        if default_provider not in providers:
            raise ValueError(f"El proveedor predeterminado '{default_provider}' no está registrado.")
        self._providers = providers
        self._default_provider = default_provider

    def get_provider(self, name: str | None = None) -> AIProvider:
        provider = self._providers.get(name or self._default_provider)
        if provider is None:
            raise ValueError(f"Proveedor de IA desconocido: {name}")
        return provider

    def select(self, task_type: str | None = None) -> AIProvider:
        """Punto de extensión para políticas por tipo de tarea/modelo.

        La política inicial conserva el proveedor configurado, de modo que
        AnthropicProvider y MockProvider siguen siendo 100% compatibles.
        """
        return self.get_provider()

    def chat(self, messages: list[AIMessage], tools: list[ToolSchema] | None = None) -> AIResponse:
        return self.select().chat(messages, tools)

    def chat_stream(self, messages: list[AIMessage], tools: list[ToolSchema] | None = None):
        yield from self.select().chat_stream(messages, tools)
