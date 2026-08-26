"""Construye el SmartHomeProvider activo a partir de la configuración.

Único punto compartido entre app.tools.registry (necesita el provider al
construir las tools, de forma eager) y app.api.v1.devices/rooms (lo
necesitan por request) — ambos obtienen la misma instancia (lru_cache).
"""
from __future__ import annotations

from functools import lru_cache

from app.config import get_settings
from app.smart_home.base import SmartHomeProvider


@lru_cache
def get_smart_home_provider() -> SmartHomeProvider:
    settings = get_settings()
    if settings.smart_home_provider == "home_assistant":
        from app.smart_home.home_assistant_provider import HomeAssistantProvider

        return HomeAssistantProvider(base_url=settings.smart_home_url, token=settings.smart_home_token)

    from app.smart_home.mock_provider import MockSmartHomeProvider

    return MockSmartHomeProvider()
