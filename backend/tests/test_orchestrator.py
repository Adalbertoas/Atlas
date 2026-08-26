from __future__ import annotations

from app.ai.base import AIMessage, AIProvider, AIResponse, ToolSchema
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
