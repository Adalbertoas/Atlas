"""query_world: consulta datos geoespaciales en vivo a Gods Eye View.

Además de responder, publica la vista que acompaña a la respuesta (la zona
encuadrada con la capa correspondiente encendida) para que el dashboard la
muestre en Mundo. Los temas que terminan en `_image` devuelven una imagen
que el cliente muestra en el chat.
"""
from __future__ import annotations

import json

from app.security.permissions import RiskLevel
from app.tools.base import Tool, ToolContext, ToolImage, ToolResult
from app.world.client import GodsEyeClient, GodsEyeError, GodsEyeResult
from app.world.state import WorldViewState, publish_result_view
from app.world.topics import TOPICS, build_arguments

DEFAULT_LIMIT = 5
MAX_LIMIT = 20
MAX_RESULT_CHARS = 3000  # el resultado va al contexto del modelo: se acota

# Temas que no son "una tool, una lista de filas" y se resuelven aparte.
_WEATHER_MAPS = {"satellite_image": "global_satellite", "radar_image": "radar"}
_SPECIAL_TOPICS = ["weather", *_WEATHER_MAPS, "camera_image"]


def _compact(value):
    """Quita nulos y vacíos: la mayoría de los campos de cada fila no vienen informados."""
    if isinstance(value, dict):
        return {k: _compact(v) for k, v in value.items() if v not in (None, "", [], {})}
    if isinstance(value, list):
        return [_compact(v) for v in value]
    return value


def _as_text(summary: str, details: dict) -> str:
    details = _compact({k: v for k, v in details.items() if k != "view"})
    text = summary
    if details:
        text += "\n" + json.dumps(details, ensure_ascii=False, separators=(",", ":"))
    if len(text) > MAX_RESULT_CHARS:
        text = text[:MAX_RESULT_CHARS] + "… (recortado)"
    return text


class QueryWorldTool(Tool):
    name = "query_world"
    description = (
        "Consulta datos del mundo en vivo: aviones, aviones militares, barcos, terremotos, incendios, "
        "satélites sobre un lugar, ciclones, lanzamientos espaciales, cámaras públicas, clima actual "
        "(weather) o un resumen de situación de una zona. Con satellite_image (nubes, mundial), "
        "radar_image (lluvia, solo EE. UU.) o camera_image (cámara pública más cercana) devuelve una "
        "imagen. También muestra el resultado en la vista Mundo del dashboard."
    )
    parameters = {
        "type": "object",
        "properties": {
            "topic": {
                "type": "string",
                "enum": [*TOPICS, *_SPECIAL_TOPICS],
                "description": "Qué consultar.",
            },
            "place": {
                "type": "string",
                "description": (
                    "Lugar de la consulta, ej. 'Madrid'. Opcional para earthquakes, cyclones y "
                    "satellite_image (mundial); no se usa en launches."
                ),
            },
            "limit": {
                "type": "integer",
                "description": f"Máximo de resultados (por defecto {DEFAULT_LIMIT}, tope {MAX_LIMIT}).",
            },
            "min_magnitude": {
                "type": "number",
                "description": "Solo para earthquakes: magnitud mínima (2.5 a 10).",
            },
        },
        "required": ["topic"],
    }
    risk_level = RiskLevel.READ_ONLY

    def __init__(self, client: GodsEyeClient, state: WorldViewState) -> None:
        self._client = client
        self._state = state

    def execute(self, params: dict, context: ToolContext) -> ToolResult:
        topic_name = str(params.get("topic", "")).strip().lower()
        place = str(params.get("place") or "").strip()
        try:
            if topic_name == "weather":
                return self._weather(place)
            if topic_name in _WEATHER_MAPS:
                return self._weather_map(_WEATHER_MAPS[topic_name], place)
            if topic_name == "camera_image":
                return self._camera_image(place)
            return self._rows(topic_name, place, params)
        except GodsEyeError as exc:
            return ToolResult(success=False, error=str(exc))

    def _publish(self, result: GodsEyeResult) -> None:
        publish_result_view(self._state, result.data, result.summary)

    def _rows(self, topic_name: str, place: str, params: dict) -> ToolResult:
        topic = TOPICS.get(topic_name)
        if topic is None:
            options = ", ".join([*TOPICS, *_SPECIAL_TOPICS])
            return ToolResult(success=False, error=f"Tema '{topic_name}' no reconocido. Opciones: {options}")

        try:
            limit = int(params.get("limit") or DEFAULT_LIMIT)
        except (TypeError, ValueError):
            limit = DEFAULT_LIMIT
        try:
            arguments = build_arguments(topic, place, max(1, min(limit, MAX_LIMIT)))
        except ValueError as exc:
            return ToolResult(success=False, error=str(exc))
        if topic_name == "earthquakes" and params.get("min_magnitude") is not None:
            arguments["min_magnitude"] = max(2.5, min(float(params["min_magnitude"]), 10))

        result = self._client.call_tool(topic.tool, arguments)
        self._publish(result)
        return ToolResult(success=True, data=_as_text(result.summary, result.data))

    def _weather(self, place: str) -> ToolResult:
        if not place:
            return ToolResult(success=False, error="Para consultar el clima indicá un lugar.")
        result = self._client.call_tool("situation_brief", {"area": {"place": place}})
        weather = (result.data.get("sections") or {}).get("weather") or {}
        if not weather.get("summary"):
            return ToolResult(success=False, error=f"No hay datos de clima disponibles para {place}.")
        self._publish(result)
        return ToolResult(
            success=True, data=_as_text(weather["summary"], (weather.get("data") or {}).get("weather") or {})
        )

    def _weather_map(self, map_kind: str, place: str) -> ToolResult:
        arguments: dict = {"map": map_kind}
        if place:
            arguments["area"] = {"place": place}
        result = self._client.call_tool("get_weather_map", arguments)
        self._publish(result)
        return self._with_images(result)

    def _camera_image(self, place: str) -> ToolResult:
        if not place:
            return ToolResult(success=False, error="Para ver una cámara indicá un lugar.")
        found = self._client.call_tool("find_cctv_cameras", {"area": {"place": place}, "limit": 1})
        cameras = found.data.get("rows") or []
        if not cameras:
            return ToolResult(success=False, error=found.summary or f"No hay cámaras públicas en {place}.")
        self._publish(found)
        camera = cameras[0]
        result = self._client.call_tool("get_cctv_snapshot", {"camera_id": str(camera.get("id"))})
        result.summary = result.summary or f"Cámara {camera.get('name') or camera.get('id')}"
        return self._with_images(result)

    @staticmethod
    def _with_images(result: GodsEyeResult) -> ToolResult:
        if not result.images:
            return ToolResult(success=False, error=f"{result.summary} (Gods Eye View no devolvió ninguna imagen.)")
        images = [ToolImage(mime_type=mime, data=data) for mime, data in result.images]
        text = _as_text(result.summary, result.data) + "\n(La imagen ya se le muestra al usuario en el chat.)"
        return ToolResult(success=True, data=text, images=images)
