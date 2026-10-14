"""Catálogo de temas del mundo: qué tool de Gods Eye View responde cada uno.

Lo comparten query_world (consultas puntuales) y las alertas (vigilancia
periódica), para que "aviones sobre Madrid" signifique lo mismo en ambos.
"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field


def _aircraft(row: dict) -> str:
    name = row.get("callsign") or row.get("registration") or row.get("id") or "aeronave"
    extras = [str(row[k]) for k in ("type_code", "operator", "origin_country") if row.get(k)]
    return f"{name} ({', '.join(extras)})" if extras else str(name)


def _earthquake(row: dict) -> str:
    return f"M{row.get('magnitude', '?')} — {row.get('place', 'ubicación desconocida')}"


def _cyclone(row: dict) -> str:
    return f"{row.get('name', 'sin nombre')} ({row.get('classification', '?')}, {row.get('wind_kt', '?')} kt)"


def _launch(row: dict) -> str:
    return f"{row.get('name', 'lanzamiento')} desde {row.get('location', '?')} ({row.get('status', '?')})"


def _generic(row: dict) -> str:
    return str(row.get("name") or row.get("callsign") or row.get("id") or row)


@dataclass(frozen=True)
class Topic:
    tool: str
    title: str  # en español, para describir consultas y alertas
    # Cómo recibe el lugar la tool de Gods Eye View: "area", "location" o None si es global.
    place_arg: str | None = "area"
    place_required: bool = True
    takes_limit: bool = True
    extra: dict = field(default_factory=dict)
    rows_key: str = "rows"
    describe: Callable[[dict], str] = _generic


TOPICS: dict[str, Topic] = {
    "aircraft": Topic("aircraft_in_area", "aviones", describe=_aircraft),
    "military_aircraft": Topic(
        "aircraft_in_area", "aviones militares", extra={"military": True}, describe=_aircraft
    ),
    "ships": Topic("vessels_in_area", "barcos"),
    "earthquakes": Topic("get_earthquakes", "terremotos", place_required=False, describe=_earthquake),
    "fires": Topic("get_active_fires", "incendios"),
    # "visual": los ~150 más brillantes; el grupo por defecto (estaciones) casi siempre da cero.
    "satellites": Topic(
        "satellites_overhead", "satélites", place_arg="location", extra={"group": "visual"}
    ),
    "cyclones": Topic(
        "get_cyclones", "ciclones", place_required=False, takes_limit=False, rows_key="storms", describe=_cyclone
    ),
    "launches": Topic("get_recent_launches", "lanzamientos espaciales", place_arg=None, describe=_launch),
    "cameras": Topic("find_cctv_cameras", "cámaras públicas"),
    "situation": Topic("situation_brief", "resumen de situación", takes_limit=False),
}


def build_arguments(topic: Topic, place: str, limit: int | None) -> dict:
    """Argumentos para la tool de Gods Eye View. Lanza ValueError si falta el lugar."""
    arguments: dict = dict(topic.extra)
    if topic.place_arg:
        if place:
            arguments[topic.place_arg] = {"place": place}
        elif topic.place_required:
            raise ValueError(f"Para consultar {topic.title} indicá un lugar.")
    if topic.takes_limit and limit is not None:
        arguments["limit"] = limit
    return arguments


def row_id(row: dict) -> str:
    return str(row.get("id") or row.get("norad") or row.get("name") or row)
