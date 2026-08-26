from __future__ import annotations

import os

import psutil

from app.security.permissions import RiskLevel
from app.tools.base import Tool, ToolContext, ToolResult


def collect_system_info() -> dict:
    """Métricas de CPU/RAM/disco. Extraído como función libre para que tanto
    la tool (invocada por la IA) como el endpoint directo
    GET /api/v1/system/status (sondeado por el cliente de escritorio, sin
    pasar por la IA) reutilicen la misma lógica."""
    cpu_percent = psutil.cpu_percent(interval=0.3)
    ram = psutil.virtual_memory()
    disk = psutil.disk_usage(os.path.abspath(os.sep))
    return {
        "cpu_percent": cpu_percent,
        "ram_percent": ram.percent,
        "ram_used_gb": round(ram.used / (1024**3), 1),
        "ram_total_gb": round(ram.total / (1024**3), 1),
        "disk_percent": disk.percent,
        "disk_used_gb": round(disk.used / (1024**3), 1),
        "disk_total_gb": round(disk.total / (1024**3), 1),
    }


class GetSystemInfoTool(Tool):
    name = "get_system_info"
    description = "Consulta el uso actual de CPU, RAM y disco del equipo."
    parameters = {"type": "object", "properties": {}, "required": []}
    risk_level = RiskLevel.READ_ONLY

    def execute(self, params: dict, context: ToolContext) -> ToolResult:
        try:
            return ToolResult(success=True, data=collect_system_info())
        except Exception as exc:  # noqa: BLE001
            return ToolResult(success=False, error=str(exc))
