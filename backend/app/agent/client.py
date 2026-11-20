"""Agente de ATLAS para la PC: con el backend en un servidor, ejecuta en esta PC
las tools que necesitan Windows (abrir programas, ventanas, portapapeles,
pantalla, archivos, volumen) y le informa al servidor la CPU/RAM.

Se conecta hacia afuera (wss://atlas.sirinetrd.com/api/v1/agent/ws): no hace
falta abrir puertos. Si se corta, reintenta solo.

    python agent.py          (desde backend/, con AGENT_SERVER_URL y AGENT_TOKEN en .env)
"""
from __future__ import annotations

import asyncio
import json
import logging
import socket
from typing import Any

from app.tools.base import Tool, ToolContext

logger = logging.getLogger("atlas.agent")

STATUS_EVERY_SECONDS = 5
MAX_BACKOFF_SECONDS = 30


def ws_url(server_url: str) -> str:
    base = server_url.strip().rstrip("/")
    if base.startswith("https://"):
        base = "wss://" + base[len("https://"):]
    elif base.startswith("http://"):
        base = "ws://" + base[len("http://"):]
    return f"{base}/api/v1/agent/ws"


def run_tool(tools: dict[str, Tool], name: str, params: dict) -> dict:
    """Ejecuta una tool local y la empaqueta como respuesta para el servidor."""
    tool = tools.get(name)
    if tool is None:
        return {"success": False, "data": None, "error": f"El agente no tiene la herramienta '{name}'.", "images": []}
    try:
        result = tool.execute(params or {}, ToolContext(db=None))  # type: ignore[arg-type]  # las tools de PC no usan la base
    except Exception as exc:  # noqa: BLE001 — una tool rota no debe tumbar al agente
        logger.exception("Falló %s", name)
        return {"success": False, "data": None, "error": f"Falló en la PC: {exc}", "images": []}
    return {
        "success": result.success,
        "data": None if result.data is None else str(result.data),
        "error": result.error,
        "images": [{"mime_type": i.mime_type, "data": i.data} for i in result.images],
    }


async def _send_status(ws: Any) -> None:
    from app.tools.system.get_system_info import collect_system_info

    while True:
        info = await asyncio.to_thread(collect_system_info)
        await ws.send(json.dumps({"type": "status", **info}))
        await asyncio.sleep(STATUS_EVERY_SECONDS)


async def _handle_call(ws: Any, tools: dict[str, Tool], message: dict) -> None:
    name = str(message.get("tool"))
    logger.info("Ejecutando %s", name)
    reply = await asyncio.to_thread(run_tool, tools, name, message.get("params") or {})
    await ws.send(json.dumps({"type": "result", "id": message.get("id"), **reply}))


async def serve(server_url: str, token: str, tools: list[Tool]) -> None:
    from websockets.asyncio.client import connect
    from websockets.exceptions import InvalidStatus

    by_name = {t.name: t for t in tools}
    url = ws_url(server_url)
    backoff = 2
    while True:
        try:
            async with connect(url, additional_headers={"Authorization": f"Bearer {token}"}, ping_interval=20, max_size=32 * 1024 * 1024) as ws:
                await ws.send(json.dumps({"type": "hello", "host": socket.gethostname(), "tools": sorted(by_name)}))
                logger.info("Conectado a %s con %d herramientas de la PC.", server_url, len(by_name))
                backoff = 2
                status = asyncio.create_task(_send_status(ws))
                try:
                    async for raw in ws:
                        message = json.loads(raw)
                        if message.get("type") == "call":
                            asyncio.create_task(_handle_call(ws, by_name, message))
                finally:
                    status.cancel()
        except InvalidStatus as exc:
            logger.error("El servidor rechazó al agente (%s). ¿AGENT_TOKEN coincide con el del servidor?", exc)
        except (OSError, asyncio.TimeoutError) as exc:
            logger.warning("Sin conexión con %s (%s).", server_url, exc)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Conexión cerrada: %s", exc)
        logger.info("Reintento en %d s.", backoff)
        await asyncio.sleep(backoff)
        backoff = min(backoff * 2, MAX_BACKOFF_SECONDS)
