"""Tests del límite de gasto en la API de Anthropic (Fase 28)."""
from __future__ import annotations

from app.ai.base import AIMessage, AIProvider, AIResponse, ToolSchema
from app.core.orchestrator import Orchestrator
from app.core.usage import check_budget, estimate_cost_usd, record_usage, spent_this_month, spent_today
from app.events.bus import EventBus
from app.security.permissions import PermissionManager
from app.tools.registry import build_default_registry


# ---------- estimate_cost_usd ----------


def test_estimate_cost_uses_sonnet_pricing_by_default():
    cost = estimate_cost_usd("claude-sonnet-4-5-20250929", input_tokens=1_000_000, output_tokens=0)
    assert cost == 3.0


def test_estimate_cost_uses_opus_pricing():
    cost = estimate_cost_usd("claude-opus-4", input_tokens=0, output_tokens=1_000_000)
    assert cost == 75.0


def test_estimate_cost_falls_back_to_sonnet_for_unknown_model():
    cost = estimate_cost_usd("claude-99-mystery", input_tokens=1_000_000, output_tokens=0)
    assert cost == 3.0  # precio de sonnet, el modelo por defecto de ATLAS


# ---------- record_usage / spent_today / spent_this_month ----------


def test_record_usage_persists_and_accumulates(db_session):
    record_usage(db_session, model="claude-sonnet-4-5", input_tokens=1000, output_tokens=500)
    record_usage(db_session, model="claude-sonnet-4-5", input_tokens=1000, output_tokens=500)

    assert spent_today(db_session) > 0
    assert spent_today(db_session) == spent_this_month(db_session)  # mismo día, mismo mes


def test_spent_today_is_zero_without_usage(db_session):
    assert spent_today(db_session) == 0.0


# ---------- check_budget ----------


def test_check_budget_allows_when_disabled(db_session, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_DAILY_BUDGET_USD", "0")
    monkeypatch.setenv("ANTHROPIC_MONTHLY_BUDGET_USD", "0")
    from app.config import get_settings

    get_settings.cache_clear()

    record_usage(db_session, model="claude-opus-4", input_tokens=10_000_000, output_tokens=10_000_000)
    assert check_budget(db_session).exceeded is False

    get_settings.cache_clear()


def test_check_budget_blocks_when_daily_limit_reached(db_session, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_DAILY_BUDGET_USD", "0.01")
    monkeypatch.setenv("ANTHROPIC_MONTHLY_BUDGET_USD", "0")
    from app.config import get_settings

    get_settings.cache_clear()

    record_usage(db_session, model="claude-sonnet-4-5", input_tokens=1_000_000, output_tokens=0)  # $3, > $0.01
    status = check_budget(db_session)

    assert status.exceeded is True
    assert "ANTHROPIC_DAILY_BUDGET_USD" in status.reason

    get_settings.cache_clear()


# ---------- Integración con el Orchestrator ----------


class _CountingProvider(AIProvider):
    """Cuenta cuántas veces se lo llamó y devuelve una respuesta con tokens
    fijos — simula un proveedor real sin pegarle a la API de Anthropic."""

    def __init__(self) -> None:
        self.calls = 0

    def chat(self, messages: list[AIMessage], tools: list[ToolSchema] | None = None) -> AIResponse:
        self.calls += 1
        return AIResponse(text="Respuesta simulada", input_tokens=1000, output_tokens=1000)


def test_orchestrator_blocks_new_turn_when_budget_exceeded(db_session, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_DAILY_BUDGET_USD", "0.001")  # cualquier llamada real ya lo supera
    monkeypatch.setenv("ANTHROPIC_MONTHLY_BUDGET_USD", "0")
    from app.config import get_settings

    get_settings.cache_clear()

    record_usage(db_session, model="claude-sonnet-4-5", input_tokens=1000, output_tokens=1000)

    provider = _CountingProvider()
    orchestrator = Orchestrator(
        ai_provider=provider,
        registry=build_default_registry(),
        permissions=PermissionManager(),
        events=EventBus(),
    )
    result = orchestrator.handle_message(db_session, "hola")

    assert provider.calls == 0  # nunca llegó a llamar al proveedor
    assert "límite de gasto" in result.reply.lower()

    get_settings.cache_clear()


def test_orchestrator_records_usage_after_successful_call(db_session):
    provider = _CountingProvider()
    orchestrator = Orchestrator(
        ai_provider=provider,
        registry=build_default_registry(),
        permissions=PermissionManager(),
        events=EventBus(),
    )
    orchestrator.handle_message(db_session, "hola")

    assert provider.calls == 1
    assert spent_today(db_session) > 0
