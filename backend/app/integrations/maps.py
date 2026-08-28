"""Cliente de mapas/rutas vía OpenStreetMap: Nominatim (geocoding) + OSRM
(ruteo). Mismo criterio que Open-Meteo (clima) y DuckDuckGo (búsqueda web):
gratis, sin API key ni cuenta — en vez de Google Maps Distance Matrix, que
funciona igual pero exige una cuenta de Google Cloud con facturación
habilitada (aunque el uso caiga dentro del crédito gratis).

Trade-off explícito, no escondido: los servidores públicos de OSRM/Nominatim
no dan tráfico en tiempo real, solo velocidad promedio por tipo de vía. La
duración es "estimada en condiciones normales", no "cuánto vas a tardar
ahora mismo" — la tool lo aclara en su respuesta, no finge precisión que no
tiene (mismo criterio que la Fase 11 con la temperatura de CPU: si no hay un
dato real, no se inventa).

Los servidores públicos (router.project-osrm.org, nominatim.openstreetmap.org)
son para uso liviano/personal, no para producción a escala — les alcanza de
sobra a un asistente de un solo usuario. Nominatim exige un User-Agent
descriptivo en cada request (su política de uso), no una API key.
"""
from __future__ import annotations

from dataclasses import dataclass

import requests

_TIMEOUT = 10
_USER_AGENT = "ATLAS-personal-assistant/1.0"
_NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
_OSRM_URL = "https://router.project-osrm.org/route/v1/driving"


@dataclass
class GeocodedPlace:
    display_name: str
    lat: float
    lon: float


@dataclass
class TravelEstimate:
    origin: str
    destination: str
    distance_km: float
    duration_min: float


def geocode(place: str) -> GeocodedPlace | None:
    response = requests.get(
        _NOMINATIM_URL,
        params={"q": place, "format": "json", "limit": 1},
        headers={"User-Agent": _USER_AGENT},
        timeout=_TIMEOUT,
    )
    response.raise_for_status()
    results = response.json()
    if not results:
        return None
    result = results[0]
    return GeocodedPlace(display_name=result["display_name"], lat=float(result["lat"]), lon=float(result["lon"]))


def get_travel_time(origin: str, destination: str) -> TravelEstimate | None:
    """None si no se pudo geocodificar alguno de los dos lugares."""
    origin_place = geocode(origin)
    if origin_place is None:
        return None
    destination_place = geocode(destination)
    if destination_place is None:
        return None

    coords = f"{origin_place.lon},{origin_place.lat};{destination_place.lon},{destination_place.lat}"
    response = requests.get(f"{_OSRM_URL}/{coords}", params={"overview": "false"}, timeout=_TIMEOUT)
    response.raise_for_status()
    payload = response.json()
    if payload.get("code") != "Ok" or not payload.get("routes"):
        return None

    route = payload["routes"][0]
    return TravelEstimate(
        origin=origin_place.display_name,
        destination=destination_place.display_name,
        distance_km=round(route["distance"] / 1000, 1),
        duration_min=round(route["duration"] / 60),
    )
