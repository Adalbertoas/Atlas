"""Límite de gasto en la API de Anthropic (Fase 28).

Hueco real: nada frenaba el consumo si algo disparaba de más — un wake word
con falsos positivos seguidos, un loop de tool calling insistente, o
simplemente uso normal que se acumula sin que nadie lo mire. Esto registra
cada llamada real a Claude y bloquea nuevas llamadas si el gasto estimado
del día/mes supera el presupuesto configurado.

El costo es una ESTIMACIÓN, no la factura real: se calcula con una tabla de
precios por familia de modelo que puede quedar desactualizada (ver
`_PRICING_PER_MILLION_TOKENS` — comparar contra anthropic.com/pricing antes
de confiar en el número para algo importante). Mismo criterio que la
temperatura de CPU en la Fase 11: es mejor una estimación aproximada y
etiquetada como tal que fingir precisión que no se tiene.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone

from sqlalchemy import Date, DateTime, Float, Integer, String
from sqlalchemy.orm import Mapped, Session, mapped_column

from app.config import get_settings
from app.core.database import Base

# USD por millón de tokens (input, output). Aproximado, por familia de
# modelo (no por versión exacta) — suficiente para un límite de gasto, no
# para reconciliar con la factura real de Anthropic.
_PRICING_PER_MILLION_TOKENS: dict[str, tuple[float, float]] = {
    "opus": (15.0, 75.0),
    "sonnet": (3.0, 15.0),
    "haiku": (1.0, 5.0),
}
_DEFAULT_PRICING = _PRICING_PER_MILLION_TOKENS["sonnet"]  # modelo por defecto de ATLAS


def _pricing_for(model: str) -> tuple[float, float]:
    model_lower = model.lower()
    for family, pricing in _PRICING_PER_MILLION_TOKENS.items():
        if family in model_lower:
            return pricing
    return _DEFAULT_PRICING


def estimate_cost_usd(model: str, input_tokens: int, output_tokens: int) -> float:
    input_price, output_price = _pricing_for(model)
    return (input_tokens / 1_000_000) * input_price + (output_tokens / 1_000_000) * output_price


class ApiUsage(Base):
    __tablename__ = "api_usage"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    model: Mapped[str] = mapped_column(String(120))
    input_tokens: Mapped[int] = mapped_column(Integer, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, default=0)
    estimated_cost_usd: Mapped[float] = mapped_column(Float, default=0.0)
    usage_date: Mapped[date] = mapped_column(Date)  # fecha local, no el datetime completo: agrupar por día es directo
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc)
    )


def record_usage(db: Session, *, model: str, input_tokens: int, output_tokens: int) -> ApiUsage:
    cost = estimate_cost_usd(model, input_tokens, output_tokens)
    entry = ApiUsage(
        model=model,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        estimated_cost_usd=cost,
        usage_date=date.today(),
    )
    db.add(entry)
    db.commit()
    return entry


def _spent_since(db: Session, since: date) -> float:
    total = (
        db.query(ApiUsage)
        .filter(ApiUsage.usage_date >= since)
        .with_entities(ApiUsage.estimated_cost_usd)
        .all()
    )
    return sum(row[0] for row in total)


def spent_today(db: Session) -> float:
    return _spent_since(db, date.today())


def spent_this_month(db: Session) -> float:
    return _spent_since(db, date.today().replace(day=1))


@dataclass
class BudgetStatus:
    exceeded: bool
    reason: str = ""


def check_budget(db: Session) -> BudgetStatus:
    """0 en cualquiera de los dos límites = sin tope (desactivado)."""
    settings = get_settings()

    if settings.anthropic_daily_budget_usd > 0:
        spent = spent_today(db)
        if spent >= settings.anthropic_daily_budget_usd:
            return BudgetStatus(
                exceeded=True,
                reason=(
                    f"Se alcanzó el límite de gasto diario en la API de Anthropic "
                    f"(${spent:.2f} de ${settings.anthropic_daily_budget_usd:.2f} estimados). "
                    "Ajustá ANTHROPIC_DAILY_BUDGET_USD en .env si querés subirlo."
                ),
            )

    if settings.anthropic_monthly_budget_usd > 0:
        spent = spent_this_month(db)
        if spent >= settings.anthropic_monthly_budget_usd:
            return BudgetStatus(
                exceeded=True,
                reason=(
                    f"Se alcanzó el límite de gasto mensual en la API de Anthropic "
                    f"(${spent:.2f} de ${settings.anthropic_monthly_budget_usd:.2f} estimados). "
                    "Ajustá ANTHROPIC_MONTHLY_BUDGET_USD en .env si querés subirlo."
                ),
            )

    return BudgetStatus(exceeded=False)
