"""Briefing diario: un resumen corto del día, armado con lo que ATLAS ya sabe.

No pasa por la IA: se arma con datos propios (notificaciones, recordatorios,
rutinas, memoria, estado del equipo) más el clima de HOME_PLACE si Gods Eye
View está corriendo. Así sirve igual con cualquier proveedor de IA y puede
dispararse solo desde una rutina programada (BRIEFING_TIME).
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from app.automation.models import Routine, RoutineAction, RoutineTrigger
from app.memory.service import list_memories
from app.notifications.service import list_notifications
from app.reminders import service as reminders
from app.tools.system.get_system_info import collect_system_info
from app.world import alerts
from app.world.client import GodsEyeClient, GodsEyeError

logger = logging.getLogger(__name__)

BRIEFING_ROUTINE = "Briefing diario"
_DAYS = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]
_MONTHS = [
    "enero", "febrero", "marzo", "abril", "mayo", "junio",
    "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre",
]  # fmt: skip
# Códigos de clima WMO (los que usa Open-Meteo, la fuente de Gods Eye View).
_WEATHER_CODES = {
    0: "despejado", 1: "mayormente despejado", 2: "parcialmente nublado", 3: "nublado",
    45: "niebla", 48: "niebla con escarcha",
    51: "llovizna leve", 53: "llovizna", 55: "llovizna intensa",
    61: "lluvia leve", 63: "lluvia", 65: "lluvia intensa",
    66: "lluvia helada", 67: "lluvia helada intensa",
    71: "nevada leve", 73: "nevada", 75: "nevada intensa", 77: "aguanieve",
    80: "chaparrones leves", 81: "chaparrones", 82: "chaparrones fuertes",
    85: "nevadas leves", 86: "nevadas fuertes",
    95: "tormenta", 96: "tormenta con granizo", 99: "tormenta fuerte con granizo",
}  # fmt: skip
DISK_WARNING_PERCENT = 90


def _greeting(now: datetime) -> str:
    if now.hour < 12:
        return "Buen día"
    return "Buenas tardes" if now.hour < 20 else "Buenas noches"


def _weather_line(client: GodsEyeClient | None, home_place: str) -> str | None:
    if client is None or not home_place:
        return None
    try:
        data = client.call_tool("situation_brief", {"area": {"place": home_place}}).data
    except GodsEyeError as exc:
        logger.info("Briefing sin clima: %s", exc)
        return None
    weather = ((data.get("sections") or {}).get("weather") or {}).get("data", {}).get("weather")
    if not weather or weather.get("temperature_c") is None:
        return None
    conditions = _WEATHER_CODES.get(weather.get("weather_code"), weather.get("conditions") or "")
    line = f"En {home_place}: {conditions}, {round(weather['temperature_c'])}°C".replace(": ,", ":")
    if weather.get("feels_like_c") is not None and abs(weather["feels_like_c"] - weather["temperature_c"]) >= 2:
        line += f" (sensación {round(weather['feels_like_c'])}°C)"
    if weather.get("wind_kph") is not None:
        line += f", viento de {round(weather['wind_kph'])} km/h"
    return line + "."


def _scheduled_routines(db: Session) -> list[str]:
    items = []
    for trigger in db.query(RoutineTrigger).filter(RoutineTrigger.type == "SCHEDULE").all():
        routine = db.get(Routine, trigger.routine_id)
        time = json.loads(trigger.config_json).get("time")
        if routine and time and routine.name != BRIEFING_ROUTINE:
            items.append(f"{routine.name} a las {time}")
    return sorted(items, key=lambda item: item.rsplit(" ", 1)[-1])


def build_briefing(
    db: Session, client: GodsEyeClient | None, home_place: str, now: datetime | None = None
) -> str:
    """`now` es hora local con tzinfo (por defecto, la actual)."""
    now = now or datetime.now().astimezone()
    lines = [f"{_greeting(now)}. Hoy es {_DAYS[now.weekday()]} {now.day} de {_MONTHS[now.month - 1]}."]

    weather = _weather_line(client, home_place)
    if weather:
        lines.append(weather)

    end_of_day = reminders.to_utc(now.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1))
    today = [r for r in reminders.list_pending(db) if r.due_at < end_of_day]
    if today:
        listed = "; ".join(f"{r.message} ({reminders.to_local(r.due_at):%H:%M})" for r in today)
        lines.append(f"Recordatorios de hoy: {listed}.")
    else:
        lines.append("No tenés recordatorios para hoy.")

    routines = _scheduled_routines(db)
    if routines:
        lines.append(f"Rutinas programadas: {'; '.join(routines)}.")

    unread = list_notifications(db, unread_only=True)
    if unread:
        latest = "; ".join(n.message for n in unread[:3])
        lines.append(f"Tenés {len(unread)} notificaciones sin leer. Las últimas: {latest}")

    watching = alerts.list_alerts(db)
    if watching:
        lines.append(f"Estoy vigilando: {'; '.join(alerts.describe(a) for a in watching)}.")

    memories = list_memories(db, limit=3)
    if memories:
        lines.append(f"Para tener presente: {'; '.join(m.content for m in memories)}.")

    system = collect_system_info()
    if system["disk_percent"] >= DISK_WARNING_PERCENT:
        lines.append(f"Atención: el disco está al {round(system['disk_percent'])}%.")

    return "\n".join(lines)


def ensure_briefing_routine(db: Session, briefing_time: str) -> None:
    """Deja la rutina del briefing alineada con BRIEFING_TIME ("HH:MM"; vacío = sin rutina)."""
    routine = db.query(Routine).filter(Routine.name == BRIEFING_ROUTINE).first()
    briefing_time = briefing_time.strip()

    if not briefing_time:
        if routine is not None:
            db.query(RoutineAction).filter(RoutineAction.routine_id == routine.id).delete()
            db.query(RoutineTrigger).filter(RoutineTrigger.routine_id == routine.id).delete()
            db.delete(routine)
            db.commit()
        return

    datetime.strptime(briefing_time, "%H:%M")  # valida el formato; ValueError si está mal
    if routine is None:
        routine = Routine(name=BRIEFING_ROUTINE)
        db.add(routine)
        db.flush()
        db.add(
            RoutineAction(
                routine_id=routine.id,
                tool_name="daily_briefing",
                params_json=json.dumps({"deliver": True}),
                order=0,
            )
        )
    db.query(RoutineTrigger).filter(RoutineTrigger.routine_id == routine.id).delete()
    db.add(
        RoutineTrigger(routine_id=routine.id, type="SCHEDULE", config_json=json.dumps({"time": briefing_time}))
    )
    db.commit()
