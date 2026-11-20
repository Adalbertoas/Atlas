"""Backend en un servidor + agente en la PC (PC_TOOLS_MODE=agent)."""
from __future__ import annotations

import concurrent.futures
import time

import pytest
from starlette.websockets import WebSocketDisconnect

from app.agent.client import run_tool, ws_url
from app.agent.hub import agent_hub
from app.config import get_settings
from app.security.permissions import RiskLevel
from app.tools.base import Tool, ToolContext, ToolResult
from app.tools.remote import PC_OFFLINE, RemoteTool

TOKEN = "clave-del-agente-de-prueba"


class _OpenApp(Tool):
    name = "open_application"
    description = "Abre un programa."
    parameters = {"type": "object", "properties": {"name": {"type": "string"}}}
    risk_level = RiskLevel.MEDIUM_RISK

    def human_description(self, params: dict) -> str:
        return f"Abrir {params.get('name')}"

    def execute(self, params: dict, context: ToolContext) -> ToolResult:
        return ToolResult(success=True, data=f"Abrí {params['name']}.")


@pytest.fixture(autouse=True)
def _fresh_hub():
    """Ningún agente "conectado" de un test anterior."""
    agent_hub._ws = None
    agent_hub.status = None
    yield
    agent_hub._ws = None
    agent_hub.status = None


@pytest.fixture()
def agent_token(monkeypatch):
    monkeypatch.setattr(get_settings(), "agent_token", TOKEN)
    yield TOKEN


def test_agent_socket_rejects_wrong_token(client, agent_token):
    with pytest.raises(WebSocketDisconnect) as exc:
        with client.websocket_connect("/api/v1/agent/ws", headers={"Authorization": "Bearer otra"}) as ws:
            ws.receive_json()
    assert exc.value.code == 4401


def test_agent_socket_disabled_without_token(client):
    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect("/api/v1/agent/ws", headers={"Authorization": "Bearer "}) as ws:
            ws.receive_json()


def test_remote_tool_runs_on_the_connected_agent(client, agent_token, auth_headers):
    remote = RemoteTool(_OpenApp(), agent_hub, timeout=5)
    assert (remote.name, remote.risk_level, remote.human_description({"name": "Excel"})) == (
        "open_application",
        RiskLevel.MEDIUM_RISK,
        "Abrir Excel",
    )
    with client.websocket_connect("/api/v1/agent/ws", headers={"Authorization": f"Bearer {TOKEN}"}) as ws:
        ws.send_json({"type": "hello", "host": "PC-de-prueba"})
        ws.send_json({"type": "status", "cpu_percent": 12.5, "ram_percent": 40.0})
        with concurrent.futures.ThreadPoolExecutor() as pool:
            pending = pool.submit(remote.execute, {"name": "Excel"}, ToolContext(db=None))
            call = ws.receive_json()
            assert call["type"] == "call" and call["tool"] == "open_application" and call["params"] == {"name": "Excel"}
            ws.send_json({"type": "result", "id": call["id"], "success": True, "data": "Abrí Excel.", "error": None, "images": []})
            result = pending.result(timeout=5)
        assert result.success and result.data == "Abrí Excel."
        assert client.get("/api/v1/agent/status", headers=auth_headers).json() == {"online": True, "host": "PC-de-prueba"}

    for _ in range(100):  # el servidor registra la desconexión un instante después
        if not agent_hub.online:
            break
        time.sleep(0.01)
    assert not agent_hub.online


def test_remote_tool_explains_when_the_pc_is_off():
    result = RemoteTool(_OpenApp(), agent_hub).execute({"name": "Excel"}, ToolContext(db=None))
    assert not result.success and result.error == PC_OFFLINE


def test_system_status_reports_the_pc_in_agent_mode(client, agent_token, auth_headers, monkeypatch):
    monkeypatch.setattr(get_settings(), "pc_tools_mode", "agent")
    assert client.get("/api/v1/system/status", headers=auth_headers).json()["pc_online"] is False
    with client.websocket_connect("/api/v1/agent/ws", headers={"Authorization": f"Bearer {TOKEN}"}) as ws:
        ws.send_json({"type": "hello", "host": "PC"})
        ws.send_json({"type": "status", "cpu_percent": 33.0, "ram_percent": 55.0})
        ws.send_json({"type": "status", "cpu_percent": 34.0, "ram_percent": 56.0})  # garantiza que el anterior ya se procesó
        for _ in range(50):
            body = client.get("/api/v1/system/status", headers=auth_headers).json()
            if body.get("cpu_percent") == 34.0:
                break
        assert body["pc_online"] is True and body["ram_percent"] == 56.0


def test_agent_client_helpers():
    assert ws_url("https://atlas.sirinetrd.com/") == "wss://atlas.sirinetrd.com/api/v1/agent/ws"
    assert ws_url("http://127.0.0.1:8000") == "ws://127.0.0.1:8000/api/v1/agent/ws"
    ok = run_tool({"open_application": _OpenApp()}, "open_application", {"name": "Paint"})
    assert ok == {"success": True, "data": "Abrí Paint.", "error": None, "images": []}
    missing = run_tool({}, "lock_computer", {})
    assert not missing["success"] and "lock_computer" in missing["error"]


def test_agent_mode_registers_pc_tools_as_remote(monkeypatch):
    from app.tools.registry import build_default_registry

    monkeypatch.setattr(get_settings(), "pc_tools_mode", "agent")
    registry = build_default_registry()
    assert isinstance(registry.get("open_application"), RemoteTool)
    assert isinstance(registry.get("lock_computer"), RemoteTool)
    assert not isinstance(registry.get("create_spreadsheet"), RemoteTool)  # el Excel se arma en el servidor
