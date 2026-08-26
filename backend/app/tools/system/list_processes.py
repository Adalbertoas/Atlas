from __future__ import annotations

import psutil

from app.security.permissions import RiskLevel
from app.tools.base import Tool, ToolContext, ToolResult

MAX_PROCESSES = 30


class ListProcessesTool(Tool):
    name = "list_processes"
    description = "Lista los procesos activos del equipo (nombre, pid, %CPU, RAM), ordenados por uso de RAM."
    parameters = {"type": "object", "properties": {}, "required": []}
    risk_level = RiskLevel.READ_ONLY

    def execute(self, params: dict, context: ToolContext) -> ToolResult:
        processes = []
        for proc in psutil.process_iter(["pid", "name", "cpu_percent", "memory_info"]):
            try:
                info = proc.info
                mem_mb = round(info["memory_info"].rss / (1024**2), 1) if info["memory_info"] else 0.0
                processes.append(
                    {
                        "pid": info["pid"],
                        "name": info["name"],
                        "cpu_percent": info["cpu_percent"],
                        "memory_mb": mem_mb,
                    }
                )
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue  # el proceso pudo cerrarse entre process_iter y leer sus datos

        processes.sort(key=lambda p: p["memory_mb"], reverse=True)
        return ToolResult(success=True, data=processes[:MAX_PROCESSES])
