"""Cliente de clima vía Open-Meteo (sin API key, sin límite de uso real).

Dos pasos: geocoding (nombre de ciudad -> lat/lon) y forecast (lat/lon ->
clima actual). Los códigos WMO de weather_code se traducen a una
descripción corta en español — Open-Meteo solo da el código numérico.
"""
from __future__ import annotations

from dataclasses import dataclass

import requests

_TIMEOUT = 10

# Subconjunto de códigos WMO (https://open-meteo.com/en/docs, sección
# "WMO Weather interpretation codes") — cubre los casos comunes, no la
# tabla completa.
_WEATHER_CODES: dict[int, str] = {
    0: "despejado",
    1: "mayormente despejado",
    2: "parcialmente nublado",
    3: "nublado",
    45: "neblina",
    48: "neblina con escarcha",
    51: "llovizna leve",
    53: "llovizna moderada",
    55: "llovizna intensa",
    61: "lluvia leve",
    63: "lluvia moderada",
    65: "lluvia intensa",
    71: "nieve leve",
    73: "nieve moderada",
    75: "nieve intensa",
    80: "chubascos leves",
    81: "chubascos moderados",
    82: "chubascos intensos",
    95: "tormenta eléctrica",
    96: "tormenta con granizo leve",
    99: "tormenta con granizo intenso",
}


@dataclass
class WeatherResult:
    city: str
    temperature_c: float
    feels_like_c: float
    humidity_pct: int
    wind_kmh: float
    description: str


def get_weather(city: str) -> WeatherResult | None:
    """None si no se encontró la ciudad."""
    geocoding = requests.get(
        "https://geocoding-api.open-meteo.com/v1/search",
        params={"name": city, "count": 1, "language": "es", "format": "json"},
        timeout=_TIMEOUT,
    )
    geocoding.raise_for_status()
    results = geocoding.json().get("results")
    if not results:
        return None
    place = results[0]

    forecast = requests.get(
        "https://api.open-meteo.com/v1/forecast",
        params={
            "latitude": place["latitude"],
            "longitude": place["longitude"],
            "current": "temperature_2m,apparent_temperature,relative_humidity_2m,wind_speed_10m,weather_code",
            "timezone": "auto",
        },
        timeout=_TIMEOUT,
    )
    forecast.raise_for_status()
    current = forecast.json()["current"]

    return WeatherResult(
        city=place.get("name", city),
        temperature_c=current["temperature_2m"],
        feels_like_c=current["apparent_temperature"],
        humidity_pct=current["relative_humidity_2m"],
        wind_kmh=current["wind_speed_10m"],
        description=_WEATHER_CODES.get(current["weather_code"], "condición desconocida"),
    )
