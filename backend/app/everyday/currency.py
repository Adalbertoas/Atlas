"""Conversión de divisas con open.er-api.com (gratis, sin clave, se actualiza a diario)."""
from __future__ import annotations

import time

from app.everyday.http import get_json
from app.web.client import WebError

RATES_URL = "https://open.er-api.com/v6/latest/{base}"
_CACHE_SECONDS = 3600
_cache: dict[str, tuple[float, dict[str, float], str]] = {}

# Nombres comunes -> código ISO, para cuando el modelo pase "pesos dominicanos".
ALIASES = {
    "dolar": "USD", "dólar": "USD", "dolares": "USD", "dólares": "USD",
    "euro": "EUR", "euros": "EUR",
    "peso dominicano": "DOP", "pesos dominicanos": "DOP",
    "peso mexicano": "MXN", "pesos mexicanos": "MXN",
    "peso argentino": "ARS", "pesos argentinos": "ARS",
    "peso colombiano": "COP", "pesos colombianos": "COP",
    "peso chileno": "CLP", "pesos chilenos": "CLP",
    "libra": "GBP", "libras": "GBP",
    "yen": "JPY", "yenes": "JPY",
    "sol": "PEN", "soles": "PEN",
    "real": "BRL", "reales": "BRL",
    "bitcoin": "BTC",
}  # fmt: skip


def normalize(code: str) -> str:
    text = code.strip().lower()
    if text in ALIASES:
        return ALIASES[text]
    code = code.strip().upper()
    if len(code) != 3 or not code.isalpha():
        raise WebError(f"«{code}» no es un código de moneda válido (ej.: USD, EUR, DOP).")
    return code


def _rates(base: str) -> tuple[dict[str, float], str]:
    cached = _cache.get(base)
    if cached and time.monotonic() - cached[0] < _CACHE_SECONDS:
        return cached[1], cached[2]
    data = get_json(RATES_URL.format(base=base))
    if data.get("result") != "success":
        raise WebError(f"No hay cotizaciones para {base}.")
    rates = {k: float(v) for k, v in (data.get("rates") or {}).items()}
    updated = str(data.get("time_last_update_utc") or "")
    _cache[base] = (time.monotonic(), rates, updated)
    return rates, updated


def convert(amount: float, source: str, target: str) -> dict:
    source, target = normalize(source), normalize(target)
    rates, updated = _rates(source)
    if target not in rates:
        raise WebError(f"No tengo cotización de {source} a {target}.")
    rate = rates[target]
    return {
        "amount": amount,
        "from": source,
        "to": target,
        "rate": rate,
        "result": round(amount * rate, 4),
        "updated": updated,
    }
