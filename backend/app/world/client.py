"""Cliente de Gods Eye View (integrations/gods-eye-view), la consola geoespacial local.

Gods Eye View expone sus herramientas por MCP sobre HTTP en `/mcp` (JSON-RPC,
sin estado: un mensaje por POST). Ese endpoint solo acepta pedidos de esta
misma máquina, así que ATLAS le habla siempre por loopback — ver
docs/gods-eye-view-integration.md.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from functools import lru_cache
from typing import Any

import requests

from app.config import get_settings


class GodsEyeError(Exception):
    """Fallo esperable al consultar Gods Eye View; el mensaje es apto para el usuario."""


@dataclass
class GodsEyeResult:
    summary: str
    data: dict[str, Any] = field(default_factory=dict)
    # (mime_type, base64) de cada imagen que devolvió la tool.
    images: list[tuple[str, str]] = field(default_factory=list)


class GodsEyeClient:
    def __init__(self, base_url: str, timeout: int = 45) -> None:
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout

    def call_tool(self, name: str, arguments: dict[str, Any]) -> GodsEyeResult:
        payload = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {"name": name, "arguments": arguments},
        }
        try:
            response = requests.post(
                f"{self._base_url}/mcp",
                json=payload,
                headers={"Accept": "application/json, text/event-stream"},
                timeout=self._timeout,
            )
            response.raise_for_status()
            body = response.json()
        except requests.ConnectionError as exc:
            raise GodsEyeError(
                f"Gods Eye View no responde en {self._base_url}. Inicialo con "
                "'npm run dev' en integrations/gods-eye-view."
            ) from exc
        except (requests.RequestException, ValueError) as exc:
            raise GodsEyeError(f"Gods Eye View devolvió una respuesta inválida ({exc}).") from exc

        if "error" in body:
            raise GodsEyeError(str(body["error"].get("message", body["error"])))

        result = body.get("result") or {}
        texts = [c.get("text", "") for c in result.get("content", []) if c.get("type") == "text"]
        summary = texts[0] if texts else ""
        if result.get("isError"):
            raise GodsEyeError(summary or "Gods Eye View no pudo responder la consulta.")
        images = [
            (c.get("mimeType", "image/png"), c.get("data", ""))
            for c in result.get("content", [])
            if c.get("type") == "image" and c.get("data")
        ]
        return GodsEyeResult(summary=summary, data=result.get("structuredContent") or {}, images=images)


@lru_cache
def get_gods_eye_client() -> GodsEyeClient | None:
    """None si GODS_EYE_URL está vacío: la integración queda desactivada."""
    url = get_settings().gods_eye_url.strip()
    return GodsEyeClient(url) if url else None
