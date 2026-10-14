"""show_world_view: lleva el globo de Gods Eye View a un lugar, con capas en vivo,
marcas dibujadas y, opcionalmente, la cámara siguiendo a un avión o satélite."""
from __future__ import annotations

import re

from app.security.permissions import RiskLevel
from app.tools.base import Tool, ToolContext, ToolResult
from app.world.client import GodsEyeClient, GodsEyeError
from app.world.state import WorldViewState, publish_result_view

# Nombres cortos para el modelo -> id de capa en Gods Eye View.
LAYERS = {
    "flights": "flights",
    "military": "military",
    "ships": "ais-live-vessels",
    "satellites": "satellites",
    "earthquakes": "earthquakes",
    "fires": "local-firms",
    "weather_radar": "weather-radar",
    "clouds": "weather-satellite",
    "lightning": "weather-lightning",
    "cyclones": "weather-cyclones",
    "wind": "wind",
    "traffic": "traffic",
    "cameras": "cctv",
    "launches": "rocket-launches",
    "cables": "telegeography-submarine-cables",
}
STYLES = ["normal", "retro", "surveillance", "thermal", "anime", "noir", "snow"]
DEFAULT_RADIUS_KM = 50

_PLACE_MARKS = ["pin", "label", "highlight", "area"]  # se ubican por nombre de lugar
_PATH_MARKS = ["arrow", "route"]  # unen lugares: hay que resolver coordenadas
MARK_COLORS = ["primary", "amber", "cyan", "green", "red"]
MAX_MARKS = 24
MAX_ROUTE_PLACES = 12
ISS_NORAD = "25544"
FOLLOW_RADIUS_KM = 100
WHOLE_EARTH = {"lat": 0, "lon": 0, "altitude_m": 20_000_000}
BBOX_MARGIN_DEG = 0.5


def _area_of(annotations: list[dict]) -> dict | None:
    """Zona que encuadra las marcas: el primer lugar nombrado, o el rectángulo de los puntos."""
    points = []
    for annotation in annotations:
        if annotation.get("target"):
            return {"place": annotation["target"]}
        points += annotation.get("points") or []
        if "latitude" in annotation:
            points.append({"latitude": annotation["latitude"], "longitude": annotation["longitude"]})
            points.append({"latitude": annotation["toLatitude"], "longitude": annotation["toLongitude"]})
    if not points:
        return None
    lats = [point["latitude"] for point in points]
    lons = [point["longitude"] for point in points]
    return {
        "bbox": [
            max(-180, min(lons) - BBOX_MARGIN_DEG),
            max(-90, min(lats) - BBOX_MARGIN_DEG),
            min(180, max(lons) + BBOX_MARGIN_DEG),
            min(90, max(lats) + BBOX_MARGIN_DEG),
        ]
    }
_ICAO24 = re.compile(r"^[0-9a-fA-F]{6}$")


class ShowWorldViewTool(Tool):
    name = "show_world_view"
    description = (
        "Muestra un lugar en el globo 3D de la vista Mundo del dashboard, opcionalmente con capas de "
        "datos en vivo (vuelos, barcos, satélites, terremotos, clima...). También puede dibujar marcas "
        "(pines, etiquetas, áreas, flechas o rutas en línea recta entre lugares) y hacer que la cámara "
        "siga a un avión o a un satélite. Usala cuando el usuario pida ver, mostrar, marcar o seguir "
        "algo en el mapa."
    )
    parameters = {
        "type": "object",
        "properties": {
            "place": {
                "type": "string",
                "description": (
                    "Nombre del lugar, ej. 'Buenos Aires' o 'Estrecho de Gibraltar'. Si es ambiguo "
                    "agregá provincia o país (ej. 'Córdoba, Argentina')."
                ),
            },
            "lat": {"type": "number", "description": "Latitud, si no se da un nombre de lugar."},
            "lon": {"type": "number", "description": "Longitud, si no se da un nombre de lugar."},
            "radius_km": {
                "type": "number",
                "description": f"Radio a encuadrar alrededor de lat/lon (por defecto {DEFAULT_RADIUS_KM}).",
            },
            "layers": {
                "type": "array",
                "items": {"type": "string", "enum": list(LAYERS)},
                "description": "Capas a encender; las demás se apagan.",
            },
            "style": {
                "type": "string",
                "enum": STYLES,
                "description": "Estilo visual: surveillance es visión nocturna, thermal es infrarrojo, retro es CRT.",
            },
            "follow_aircraft": {
                "type": "string",
                "description": "Seguir a un avión: su vuelo (callsign, ej. 'ARG1676'), matrícula o código ICAO.",
            },
            "follow_satellite": {
                "type": "string",
                "description": "Seguir a un satélite: nombre (ej. 'ISS', 'HUBBLE') o número NORAD.",
            },
            "cockpit": {"type": "boolean", "description": "Con follow_aircraft: vista desde la cabina."},
            "marks": {
                "type": "array",
                "description": "Marcas a dibujar sobre el globo.",
                "items": {
                    "type": "object",
                    "properties": {
                        "type": {
                            "type": "string",
                            "enum": [*_PLACE_MARKS, *_PATH_MARKS],
                            "description": "pin/label/highlight/area marcan un lugar; arrow y route unen lugares.",
                        },
                        "place": {"type": "string", "description": "Lugar a marcar (pin, label, highlight, area)."},
                        "places": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": (
                                "Lugares a unir en orden: 2 para arrow, 2 a 12 para route. Con país o "
                                "provincia si el nombre es ambiguo."
                            ),
                        },
                        "label": {"type": "string", "description": "Texto de la marca."},
                        "color": {"type": "string", "enum": MARK_COLORS},
                    },
                    "required": ["type"],
                },
            },
        },
        "required": [],
    }
    risk_level = RiskLevel.LOW_RISK  # solo cambia lo que muestra una pantalla: se ejecuta directo

    def __init__(self, client: GodsEyeClient, state: WorldViewState) -> None:
        self._client = client
        self._state = state

    def execute(self, params: dict, context: ToolContext) -> ToolResult:
        try:
            return self._execute(params)
        except GodsEyeError as exc:
            return ToolResult(success=False, error=str(exc))
        except ValueError as exc:
            return ToolResult(success=False, error=str(exc))

    def _execute(self, params: dict) -> ToolResult:
        arguments: dict = {}
        shown: list[str] = []

        place = str(params.get("place") or "").strip()
        if place:
            arguments["area"] = {"place": place}
            shown.append(place)
        elif params.get("lat") is not None and params.get("lon") is not None:
            arguments["area"] = {
                "lat": params["lat"],
                "lon": params["lon"],
                "radius_km": params.get("radius_km") or DEFAULT_RADIUS_KM,
            }
            shown.append("las coordenadas pedidas")

        layers = params.get("layers") or []
        unknown = [layer for layer in layers if layer not in LAYERS]
        if unknown:
            raise ValueError(f"Capas no reconocidas: {', '.join(unknown)}. Opciones: {', '.join(LAYERS)}")
        if layers:
            arguments["layers"] = [LAYERS[layer] for layer in layers]
        if params.get("style"):
            arguments["style"] = params["style"]

        # Gods Eye View exige siempre un encuadre. Si el usuario no nombró un lugar,
        # se deduce de lo pedido: la posición del avión, o la zona que ocupan las marcas.
        fallback_area: dict | None = None

        if params.get("follow_aircraft"):
            arguments["follow"], label, fallback_area = self._resolve_aircraft(str(params["follow_aircraft"]))
            if params.get("cockpit"):
                arguments["follow"]["cockpit"] = True
            shown.append(f"siguiendo al avión {label}")
        elif params.get("follow_satellite"):
            arguments["follow"], label = self._resolve_satellite(str(params["follow_satellite"]))
            shown.append(f"siguiendo a {label}")

        marks = params.get("marks") or []
        if marks:
            arguments["annotations"] = self._annotations(marks)
            shown.append(f"{len(marks)} marca(s)")
            fallback_area = fallback_area or _area_of(arguments["annotations"])

        if not arguments:
            raise ValueError("Indicá un lugar, coordenadas, capas, marcas, un estilo o algo para seguir.")
        if "area" not in arguments:
            if fallback_area:
                arguments["area"] = fallback_area
            else:
                arguments["camera"] = dict(WHOLE_EARTH)  # ej. solo capas, o seguir un satélite

        result = self._client.call_tool("show_in_gods_eye_view", arguments)
        if not publish_result_view(self._state, result.data, result.summary):
            return ToolResult(success=False, error="Gods Eye View no devolvió una vista para mostrar.")

        with_layers = f" con las capas: {', '.join(layers)}" if layers else ""
        return ToolResult(
            success=True,
            data=f"Mostrando {', '.join(shown) or 'el globo'} en la vista Mundo del dashboard{with_layers}.",
        )

    def _resolve_aircraft(self, query: str) -> tuple[dict, str, dict | None]:
        """(a quién seguir, cómo nombrarlo, zona donde está ahora)."""
        query = query.strip()
        searches = [{"callsign": query.replace(" ", "").upper()}, {"registration": query.upper()}]
        if _ICAO24.match(query):
            searches.insert(0, {"icao24": query.lower()})
        for search in searches:
            rows = self._client.call_tool("find_aircraft", {**search, "limit": 1}).data.get("rows") or []
            if rows:
                row = rows[0]
                kind = "military_aircraft" if row.get("military") or row.get("feed") == "military" else "aircraft"
                area = None
                if row.get("lat") is not None and row.get("lon") is not None:
                    area = {"lat": row["lat"], "lon": row["lon"], "radius_km": FOLLOW_RADIUS_KM}
                return {"kind": kind, "id": str(row["id"])}, row.get("callsign") or query, area
        raise ValueError(f"No encontré ningún avión en vuelo con '{query}' ahora mismo.")

    def _resolve_satellite(self, query: str) -> tuple[dict, str]:
        query = query.strip()
        if query.isdigit():
            return {"kind": "satellite", "id": query}, f"el satélite {query}"
        if query.upper() in {"ISS", "EEI", "ESTACION ESPACIAL", "ESTACIÓN ESPACIAL"}:
            return {"kind": "satellite", "id": ISS_NORAD}, "la ISS"
        # Gods Eye View no tiene un buscador de satélites: se le pide la próxima
        # pasada sobre un punto cualquiera solo para que resuelva nombre -> NORAD.
        data = self._client.call_tool(
            "next_satellite_pass", {"location": {"lat": 0, "lon": 0}, "satellite": query, "group": "visual"}
        ).data
        if not data.get("norad"):
            raise ValueError(f"No encontré ningún satélite llamado '{query}'.")
        return {"kind": "satellite", "id": str(data["norad"])}, data.get("satellite") or query

    def _locate(self, place: str) -> dict:
        """Coordenadas de un lugar, usando el geocodificador de Gods Eye View."""
        view = self._client.call_tool("show_in_gods_eye_view", {"area": {"place": place}}).data.get("view") or {}
        camera = view.get("camera") or {}
        if camera.get("lat") is None:
            raise ValueError(f"No pude ubicar '{place}'.")
        return {"latitude": camera["lat"], "longitude": camera["lon"]}

    def _annotations(self, marks: list) -> list[dict]:
        if len(marks) > MAX_MARKS:
            raise ValueError(f"Demasiadas marcas: el máximo es {MAX_MARKS}.")
        annotations = []
        for mark in marks:
            kind = str(mark.get("type", "")).strip().lower()
            annotation: dict = {"type": kind}
            if mark.get("label"):
                annotation["label"] = str(mark["label"])[:120]
            if mark.get("color") in MARK_COLORS:
                annotation["color"] = mark["color"]

            if kind in _PLACE_MARKS:
                target = str(mark.get("place") or "").strip()
                if not target:
                    raise ValueError(f"La marca '{kind}' necesita un lugar (place).")
                annotation["target"] = target
            elif kind in _PATH_MARKS:
                places = [str(p).strip() for p in (mark.get("places") or []) if str(p).strip()]
                if kind == "arrow" and len(places) != 2:
                    raise ValueError("Una flecha necesita exactamente 2 lugares (places).")
                if kind == "route" and not 2 <= len(places) <= MAX_ROUTE_PLACES:
                    raise ValueError(f"Una ruta necesita entre 2 y {MAX_ROUTE_PLACES} lugares (places).")
                points = [self._locate(p) for p in places]
                if kind == "arrow":
                    annotation.update(points[0])
                    annotation["toLatitude"] = points[1]["latitude"]
                    annotation["toLongitude"] = points[1]["longitude"]
                else:
                    annotation["points"] = points
            else:
                options = ", ".join([*_PLACE_MARKS, *_PATH_MARKS])
                raise ValueError(f"Tipo de marca '{kind}' no reconocido. Opciones: {options}")
            annotations.append(annotation)
        return annotations
