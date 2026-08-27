from __future__ import annotations

import os
import time

import psutil

from app.security.permissions import RiskLevel
from app.tools.base import Tool, ToolContext, ToolResult

# Estado del último muestreo de red, para calcular throughput (psutil solo
# da contadores acumulados desde el arranque — la velocidad actual es la
# derivada entre dos lecturas). A nivel de módulo: el dashboard sondea este
# endpoint cada pocos segundos, así que la ventana entre llamadas es el
# intervalo natural de muestreo.
_last_net_sample: tuple[float, int, int] | None = None


def _network_mbps() -> dict:
    """Velocidad de red actual en Mbps, comparando contra el muestreo previo.
    La primera llamada devuelve 0 (no hay contra qué comparar todavía)."""
    global _last_net_sample
    counters = psutil.net_io_counters()
    now = time.monotonic()
    sample = (now, counters.bytes_sent, counters.bytes_recv)

    if _last_net_sample is None:
        _last_net_sample = sample
        return {"net_sent_mbps": 0.0, "net_recv_mbps": 0.0}

    prev_time, prev_sent, prev_recv = _last_net_sample
    elapsed = now - prev_time
    _last_net_sample = sample
    if elapsed <= 0:
        return {"net_sent_mbps": 0.0, "net_recv_mbps": 0.0}

    # bytes/s -> megabits/s (*8 bits, /1e6). Se usa 1e6 y no 1024² a propósito:
    # las velocidades de red se miden en megabits decimales, como las anuncian
    # los proveedores de internet.
    return {
        "net_sent_mbps": round((counters.bytes_sent - prev_sent) * 8 / elapsed / 1e6, 1),
        "net_recv_mbps": round((counters.bytes_recv - prev_recv) * 8 / elapsed / 1e6, 1),
    }


# True/False una vez que se determinó si este equipo expone temperatura;
# None mientras no se probó. Sin esto, cada llamada a /system/status (que el
# dashboard sondea cada 3s) abriría una conexión WMI nueva — lenta, y encima
# dejaba un "Win32 exception occurred releasing IUnknown" al liberar el COM.
_temp_supported: bool | None = None


def _read_temperature() -> float | None:
    """Un intento de lectura, sin caché. En Windows psutil.sensors_temperatures()
    directamente no existe (es solo Linux/FreeBSD), así que se cae a WMI."""
    sensors = getattr(psutil, "sensors_temperatures", None)
    if sensors is not None:
        try:
            for entries in sensors().values():
                for entry in entries:
                    if entry.current:
                        return round(float(entry.current), 1)
        except Exception:  # noqa: BLE001 — nunca romper /status por un sensor
            pass

    try:
        import wmi  # type: ignore[import-not-found]

        # MSAcpi_ThermalZoneTemperature reporta en décimas de Kelvin. Muchas
        # placas de escritorio simplemente no lo exponen (confirmado en la
        # PC de desarrollo) — ahí esto lanza y se devuelve None.
        for zone in wmi.WMI(namespace="root\\wmi").MSAcpi_ThermalZoneTemperature():
            return round(zone.CurrentTemperature / 10.0 - 273.15, 1)
    except Exception:  # noqa: BLE001 — wmi no instalado, o la placa no lo expone
        pass

    return None


def _cpu_temperature() -> float | None:
    """Temperatura de CPU en °C, o None si el equipo no la expone.

    Si el primer intento falla, se recuerda y no se vuelve a intentar: el
    soporte de sensores no aparece a mitad de la ejecución, y reintentar en
    cada sondeo del dashboard solo costaría latencia."""
    global _temp_supported
    if _temp_supported is False:
        return None

    temperature = _read_temperature()
    _temp_supported = temperature is not None
    return temperature


def collect_system_info() -> dict:
    """Métricas de CPU/RAM/disco/red/temperatura. Extraído como función libre
    para que tanto la tool (invocada por la IA) como el endpoint directo
    GET /api/v1/system/status (sondeado por el cliente de escritorio, sin
    pasar por la IA) reutilicen la misma lógica."""
    cpu_percent = psutil.cpu_percent(interval=0.3)
    ram = psutil.virtual_memory()
    disk = psutil.disk_usage(os.path.abspath(os.sep))
    info = {
        "cpu_percent": cpu_percent,
        "ram_percent": ram.percent,
        "ram_used_gb": round(ram.used / (1024**3), 1),
        "ram_total_gb": round(ram.total / (1024**3), 1),
        "disk_percent": disk.percent,
        "disk_used_gb": round(disk.used / (1024**3), 1),
        "disk_total_gb": round(disk.total / (1024**3), 1),
        "uptime_seconds": int(time.time() - psutil.boot_time()),
        "cpu_temp_c": _cpu_temperature(),  # None si el equipo no lo expone
    }
    info.update(_network_mbps())
    return info


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
