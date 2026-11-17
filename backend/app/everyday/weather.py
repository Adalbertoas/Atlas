"""Clima actual y pronóstico con Open-Meteo (gratis, sin clave).

El lugar se resuelve con su geocodificador. "Santo Domingo, República
Dominicana" se busca como "Santo Domingo" y se prefiere el resultado cuyo país
o región coincide con lo que va después de la coma.
"""
from __future__ import annotations

import unicodedata
from dataclasses import asdict, dataclass
from datetime import date as _date

from app.everyday.http import get_json
from app.web.client import WebError

GEOCODE_URL = "https://geocoding-api.open-meteo.com/v1/search"
FORECAST_URL = "https://api.open-meteo.com/v1/forecast"

# Códigos WMO que usa Open-Meteo -> (descripción, icono para la interfaz).
WMO = {
    0: ("despejado", "sun"),
    1: ("mayormente despejado", "sun"),
    2: ("parcialmente nublado", "partly"),
    3: ("nublado", "cloud"),
    45: ("niebla", "fog"),
    48: ("niebla con escarcha", "fog"),
    51: ("llovizna ligera", "drizzle"),
    53: ("llovizna", "drizzle"),
    55: ("llovizna intensa", "drizzle"),
    56: ("llovizna helada", "drizzle"),
    57: ("llovizna helada intensa", "drizzle"),
    61: ("lluvia ligera", "rain"),
    63: ("lluvia", "rain"),
    65: ("lluvia intensa", "rain"),
    66: ("lluvia helada", "rain"),
    67: ("lluvia helada intensa", "rain"),
    71: ("nevada ligera", "snow"),
    73: ("nevada", "snow"),
    75: ("nevada intensa", "snow"),
    77: ("granizo fino", "snow"),
    80: ("chubascos ligeros", "rain"),
    81: ("chubascos", "rain"),
    82: ("chubascos fuertes", "rain"),
    85: ("chubascos de nieve", "snow"),
    86: ("chubascos de nieve fuertes", "snow"),
    95: ("tormenta", "storm"),
    96: ("tormenta con granizo", "storm"),
    99: ("tormenta fuerte con granizo", "storm"),
}  # fmt: skip

_DAY_NAMES = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]


@dataclass
class Place:
    name: str
    region: str
    country: str
    latitude: float
    longitude: float

    @property
    def label(self) -> str:
        return ", ".join(part for part in (self.name, self.region, self.country) if part)


@dataclass
class DayForecast:
    date: str
    day_name: str
    description: str
    icon: str
    max_c: float
    min_c: float
    rain_chance: int | None


@dataclass
class Weather:
    place: str
    temperature_c: float
    feels_like_c: float
    humidity: int
    wind_kmh: float
    description: str
    icon: str
    is_day: bool
    days: list[DayForecast]

    def to_dict(self) -> dict:
        return asdict(self)

    def summary(self) -> str:
        lines = [
            f"{self.place}: {self.description}, {self.temperature_c:.0f} °C "
            f"(sensación {self.feels_like_c:.0f} °C), humedad {self.humidity} %, viento {self.wind_kmh:.0f} km/h."
        ]
        for day in self.days:
            rain = f", lluvia {day.rain_chance} %" if day.rain_chance is not None else ""
            lines.append(f"- {day.day_name} {day.date}: {day.description}, {day.min_c:.0f}–{day.max_c:.0f} °C{rain}")
        return "\n".join(lines)


def _plain(text: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", text.lower()) if unicodedata.category(c) != "Mn").strip()


def geocode(query: str) -> Place:
    name, _, hint = query.partition(",")
    name, hint = name.strip(), _plain(hint)
    if not name:
        raise WebError("Falta el nombre del lugar.")
    data = get_json(GEOCODE_URL, {"name": name, "count": 10, "language": "es", "format": "json"})
    results = data.get("results") or []
    if not results:
        raise WebError(f"No encontré el lugar «{query}».")
    chosen = results[0]
    if hint:
        for result in results:
            where = _plain(" ".join(str(result.get(k) or "") for k in ("country", "admin1", "country_code")))
            if hint in where or any(word in where for word in hint.split() if len(word) > 3):
                chosen = result
                break
    return Place(
        name=chosen.get("name", name),
        region=chosen.get("admin1") or "",
        country=chosen.get("country") or "",
        latitude=float(chosen["latitude"]),
        longitude=float(chosen["longitude"]),
    )


def get_weather(query: str, days: int = 3) -> Weather:
    place = geocode(query)
    days = max(1, min(int(days), 7))
    data = get_json(
        FORECAST_URL,
        {
            "latitude": place.latitude,
            "longitude": place.longitude,
            "current": "temperature_2m,apparent_temperature,relative_humidity_2m,weather_code,wind_speed_10m,is_day",
            "daily": "weather_code,temperature_2m_max,temperature_2m_min,precipitation_probability_max",
            "timezone": "auto",
            "forecast_days": days,
        },
    )
    try:
        current = data["current"]
        daily = data["daily"]
        code = int(current["weather_code"])
        description, icon = WMO.get(code, ("condición desconocida", "cloud"))
        forecast: list[DayForecast] = []
        rain = daily.get("precipitation_probability_max") or [None] * len(daily["time"])
        for i, date in enumerate(daily["time"]):
            day_code = int(daily["weather_code"][i])
            day_desc, day_icon = WMO.get(day_code, ("condición desconocida", "cloud"))
            year, month, day = (int(x) for x in date.split("-"))
            forecast.append(
                DayForecast(
                    date=f"{day:02d}/{month:02d}",
                    day_name="hoy" if i == 0 else "mañana" if i == 1 else _DAY_NAMES[_date(year, month, day).weekday()],
                    description=day_desc,
                    icon=day_icon,
                    max_c=float(daily["temperature_2m_max"][i]),
                    min_c=float(daily["temperature_2m_min"][i]),
                    rain_chance=None if rain[i] is None else int(rain[i]),
                )
            )
        return Weather(
            place=place.label,
            temperature_c=float(current["temperature_2m"]),
            feels_like_c=float(current["apparent_temperature"]),
            humidity=int(current["relative_humidity_2m"]),
            wind_kmh=float(current["wind_speed_10m"]),
            description=description,
            icon=icon if int(current.get("is_day", 1)) else ("moon" if icon == "sun" else icon),
            is_day=bool(int(current.get("is_day", 1))),
            days=forecast,
        )
    except (KeyError, TypeError, ValueError, IndexError) as exc:
        raise WebError("El servicio del clima devolvió datos incompletos.") from exc
