from __future__ import annotations

from app.integrations.maps import get_travel_time
from app.security.permissions import RiskLevel
from app.tools.base import Tool, ToolContext, ToolResult


class GetTravelTimeTool(Tool):
    name = "get_travel_time"
    description = (
        "Calcula distancia y tiempo estimado de viaje en auto entre dos lugares "
        "(ciudades, direcciones, lugares conocidos). Usar para '¿cuánto tardo en llegar a X?', "
        "'¿qué distancia hay entre X e Y?'. El tiempo es una estimación en condiciones normales "
        "de tránsito, no tráfico en tiempo real — aclarar esto en la respuesta."
    )
    parameters = {
        "type": "object",
        "properties": {
            "origin": {"type": "string", "description": "Lugar de partida, ej. 'Santo Domingo'."},
            "destination": {"type": "string", "description": "Lugar de destino, ej. 'Santiago, RD'."},
        },
        "required": ["origin", "destination"],
    }
    risk_level = RiskLevel.READ_ONLY

    def execute(self, params: dict, context: ToolContext) -> ToolResult:
        origin = (params.get("origin") or "").strip()
        destination = (params.get("destination") or "").strip()
        if not origin or not destination:
            return ToolResult(success=False, error="Faltan 'origin' y/o 'destination'.")

        try:
            estimate = get_travel_time(origin, destination)
        except Exception as exc:  # noqa: BLE001
            return ToolResult(success=False, error=f"No se pudo calcular la ruta: {exc}")

        if estimate is None:
            return ToolResult(
                success=True, data=f"No pude encontrar una ruta entre '{origin}' y '{destination}'."
            )

        return ToolResult(
            success=True,
            data=(
                f"De {estimate.origin} a {estimate.destination}: {estimate.distance_km} km, "
                f"~{estimate.duration_min} min en auto (estimado, sin tráfico en tiempo real)."
            ),
        )
