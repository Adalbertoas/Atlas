"""Conexión entre el servidor de ATLAS (en la nube) y el agente que corre en la PC.

Con el backend en un servidor Linux, las herramientas que tocan la PC (abrir
apps, ventanas, portapapeles, volumen, capturas de pantalla, archivos) no se
pueden ejecutar ahí. El agente de la PC abre un WebSocket hacia el servidor
(/api/v1/agent/ws) y el servidor le pide ejecutar cada una de esas tools.

Las tools corren en hilos (el Orchestrator es síncrono) y el WebSocket vive en
el event loop de FastAPI: `call()` cruza de uno a otro con
run_coroutine_threadsafe.
"""
from __future__ import annotations

import asyncio
import threading
import time
import uuid
from typing import Any

STATUS_FRESH_SECONDS = 20


class AgentOffline(RuntimeError):
    """No hay ningún agente conectado (la PC está apagada o el agente cerrado)."""


class AgentHub:
    def __init__(self) -> None:
        self._ws: Any = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._loop_thread: int | None = None
        self._pending: dict[str, asyncio.Future] = {}
        self._lock = threading.Lock()
        self.host: str | None = None
        self.status: dict | None = None
        self.status_at = 0.0

    @property
    def online(self) -> bool:
        return self._ws is not None

    def fresh_status(self) -> dict | None:
        """CPU/RAM de la PC si el agente las informó hace poco."""
        if self.online and self.status and time.monotonic() - self.status_at < STATUS_FRESH_SECONDS:
            return self.status
        return None

    async def attach(self, ws: Any, host: str | None) -> None:
        old = self._ws
        with self._lock:
            self._ws = ws
            self._loop = asyncio.get_running_loop()
            self._loop_thread = threading.get_ident()
            self.host = host
        if old is not None and old is not ws:
            # Un agente nuevo (la PC se reconectó) reemplaza al anterior.
            try:
                await old.close(code=4000)
            except Exception:  # noqa: BLE001
                pass

    async def detach(self, ws: Any) -> None:
        with self._lock:
            if self._ws is not ws:
                return
            self._ws = None
            self.status = None
            pending = list(self._pending.values())
            self._pending.clear()
        for future in pending:
            if not future.done():
                future.set_exception(AgentOffline("El agente de la PC se desconectó."))

    async def handle(self, message: dict) -> None:
        kind = message.get("type")
        if kind == "result":
            future = self._pending.pop(str(message.get("id")), None)
            if future is not None and not future.done():
                future.set_result(message)
        elif kind == "status":
            self.status = {k: message.get(k) for k in ("cpu_percent", "ram_percent", "ram_used_gb", "ram_total_gb", "disk_percent")}
            self.status_at = time.monotonic()

    async def _call(self, tool: str, params: dict, timeout: float) -> dict:
        ws = self._ws
        if ws is None:
            raise AgentOffline("No hay agente conectado.")
        request_id = uuid.uuid4().hex
        future = asyncio.get_running_loop().create_future()
        self._pending[request_id] = future
        try:
            await ws.send_json({"type": "call", "id": request_id, "tool": tool, "params": params})
            return await asyncio.wait_for(future, timeout)
        finally:
            self._pending.pop(request_id, None)

    def call(self, tool: str, params: dict, timeout: float = 60) -> dict:
        """Ejecuta `tool` en la PC y devuelve {"success", "data", "error", "images"}.
        Se llama desde un hilo (nunca desde el event loop: se trabaría)."""
        loop = self._loop
        if not self.online or loop is None:
            raise AgentOffline("No hay agente conectado.")
        if threading.get_ident() == self._loop_thread:
            raise RuntimeError("AgentHub.call() no se puede usar desde el event loop.")
        future = asyncio.run_coroutine_threadsafe(self._call(tool, params, timeout), loop)
        return future.result(timeout + 5)


agent_hub = AgentHub()
