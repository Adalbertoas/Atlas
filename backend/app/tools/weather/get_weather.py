from __future__ import annotations

from app.integrations.weather import get_weather
from app.security.permissions import RiskLevel
from app.tools.base import Tool, ToolContext, ToolResult


class GetWeatherTool(Tool):
    name = "get_weather"
    description = "Devuelve el clima actual de una ciudad: temperatura, sensación térmica, humedad, viento."
    parameters = {
        "type": "object",
        "properties": {
            "city": {"type": "string", "description": "Ciudad a consultar, ej. 'Buenos Aires'."},
        },
        "required": ["city"],
    }
    risk_level = RiskLevel.READ_ONLY

    def execute(self, params: dict, context: ToolContext) -> ToolResult:
        city = params.get("city", "").strip()
        if not city:
            return ToolResult(success=False, error="Falta el parámetro 'city'.")

        try:
            result = get_weather(city)
        except Exception as exc:  # noqa: BLE001
            return ToolResult(success=False, error=f"No se pudo consultar el clima: {exc}")

        if result is None:
            return ToolResult(success=True, data=f"No encontré la ciudad '{city}'.")

        return ToolResult(
            success=True,
            data=(
                f"{result.city}: {result.description}, {result.temperature_c}°C "
                f"(sensación {result.feels_like_c}°C), humedad {result.humidity_pct}%, "
                f"viento {result.wind_kmh} km/h."
            ),
        )
