"""Tools para crear, listar y borrar alertas del mundo (app/world/alerts.py)."""
from __future__ import annotations

from app.security.permissions import RiskLevel
from app.tools.base import Tool, ToolContext, ToolResult
from app.world import alerts


class CreateWorldAlertTool(Tool):
    name = "create_world_alert"
    description = (
        "Crea una alerta que vigila el mundo y notifica cuando aparece algo nuevo: terremotos (con "
        "magnitud mínima), aviones, aviones militares, barcos, incendios, ciclones o lanzamientos en "
        "un lugar, o las pasadas de un satélite (satellite_pass, por defecto la ISS) sobre un lugar. "
        "Usala cuando el usuario diga 'avisame si/cuando...' sobre algo de este tipo."
    )
    parameters = {
        "type": "object",
        "properties": {
            "topic": {
                "type": "string",
                "enum": [*alerts.ALERT_TOPICS, alerts.SATELLITE_PASS],
                "description": "Qué vigilar.",
            },
            "place": {
                "type": "string",
                "description": "Lugar a vigilar. Opcional para earthquakes, cyclones y launches (mundial).",
            },
            "min_magnitude": {"type": "number", "description": "Solo earthquakes: magnitud mínima."},
            "satellite": {"type": "string", "description": "Solo satellite_pass: nombre del satélite."},
            "every_minutes": {
                "type": "integer",
                "description": f"Cada cuánto revisar (por defecto {alerts.DEFAULT_INTERVAL_MINUTES}).",
            },
        },
        "required": ["topic"],
    }
    risk_level = RiskLevel.LOW_RISK  # solo consulta datos públicos y notifica; se borra cuando quieras

    def execute(self, params: dict, context: ToolContext) -> ToolResult:
        try:
            alert = alerts.create_alert(
                context.db,
                topic=str(params.get("topic", "")),
                place=str(params.get("place") or ""),
                min_magnitude=params.get("min_magnitude"),
                interval_minutes=params.get("every_minutes"),
                satellite=str(params.get("satellite") or ""),
            )
        except (ValueError, TypeError) as exc:
            return ToolResult(success=False, error=str(exc))
        return ToolResult(
            success=True,
            data=(
                f"Alerta creada (id={alert.id}): {alerts.describe(alert)}, revisando cada "
                f"{alert.interval_minutes} minutos. Aviso por notificación cuando haya novedades."
            ),
        )


class ListWorldAlertsTool(Tool):
    name = "list_world_alerts"
    description = "Lista las alertas del mundo activas, con su id."
    parameters = {"type": "object", "properties": {}, "required": []}
    risk_level = RiskLevel.READ_ONLY

    def execute(self, params: dict, context: ToolContext) -> ToolResult:
        items = alerts.list_alerts(context.db)
        if not items:
            return ToolResult(success=True, data="No hay alertas del mundo activas.")
        return ToolResult(
            success=True,
            data="; ".join(f"id={a.id}: {alerts.describe(a)} (cada {a.interval_minutes} min)" for a in items),
        )


class DeleteWorldAlertTool(Tool):
    name = "delete_world_alert"
    description = "Borra una alerta del mundo por su id (ver list_world_alerts)."
    parameters = {
        "type": "object",
        "properties": {"alert_id": {"type": "integer", "description": "Id de la alerta."}},
        "required": ["alert_id"],
    }
    risk_level = RiskLevel.LOW_RISK

    def execute(self, params: dict, context: ToolContext) -> ToolResult:
        try:
            alert_id = int(params.get("alert_id"))
        except (TypeError, ValueError):
            return ToolResult(success=False, error="El parámetro 'alert_id' debe ser un número.")
        if not alerts.delete_alert(context.db, alert_id):
            return ToolResult(success=False, error=f"No hay ninguna alerta con id {alert_id}.")
        return ToolResult(success=True, data=f"Alerta {alert_id} borrada.")
