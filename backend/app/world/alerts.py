"""Alertas del mundo: vigilan un tema de Gods Eye View y avisan cuando aparece algo nuevo.

"Avisame si hay un terremoto mayor a 5 cerca de Chile" crea una alerta que
se revisa cada pocos minutos (app/core/background.py). La primera revisión
solo toma nota de lo que ya había: se avisa de lo que aparece después.

El tema `satellite_pass` funciona distinto: avisa una vez por cada pasada
del satélite sobre el lugar, poco antes de que salga.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import DateTime, Float, Integer, String, Text
from sqlalchemy.orm import Mapped, Session, mapped_column

from app.core.database import Base
from app.events.bus import EventBus
from app.notifications.service import notify
from app.world.client import GodsEyeClient, GodsEyeError
from app.world.topics import TOPICS, build_arguments, row_id

logger = logging.getLogger(__name__)

# Temas que tiene sentido vigilar (satellites/cameras/situation no generan "novedades").
ALERT_TOPICS = ["earthquakes", "aircraft", "military_aircraft", "ships", "fires", "cyclones", "launches"]
SATELLITE_PASS = "satellite_pass"

DEFAULT_INTERVAL_MINUTES = 10
MIN_INTERVAL_MINUTES = 2
MAX_ROWS = 50  # filas que se piden por revisión
MAX_SEEN = 500  # ids recordados por alerta
MAX_ITEMS_PER_MESSAGE = 3
PASS_LEAD_MINUTES = 30  # con cuánta anticipación se avisa una pasada de satélite


def utcnow() -> datetime:
    """UTC sin tzinfo: SQLite devuelve los DateTime así y no se pueden comparar con aware."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


class WorldAlert(Base):
    __tablename__ = "world_alerts"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    topic: Mapped[str] = mapped_column(String(40))
    place: Mapped[str] = mapped_column(String(200), default="")
    min_magnitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    satellite: Mapped[str] = mapped_column(String(80), default="")  # solo satellite_pass; vacío = ISS
    interval_minutes: Mapped[int] = mapped_column(Integer, default=DEFAULT_INTERVAL_MINUTES)
    # JSON con los ids ya vistos. None = todavía no se hizo la primera revisión.
    seen_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_checked_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


def describe(alert: WorldAlert) -> str:
    if alert.topic == SATELLITE_PASS:
        return f"pasadas de {alert.satellite or 'la ISS'} sobre {alert.place}"
    text = TOPICS[alert.topic].title
    if alert.min_magnitude is not None:
        text += f" de magnitud {alert.min_magnitude:g} o más"
    return f"{text} en {alert.place}" if alert.place else f"{text} en todo el mundo"


def to_dict(alert: WorldAlert) -> dict:
    return {
        "id": alert.id,
        "topic": alert.topic,
        "place": alert.place,
        "min_magnitude": alert.min_magnitude,
        "interval_minutes": alert.interval_minutes,
        "description": describe(alert),
        "last_checked_at": alert.last_checked_at.isoformat() + "Z" if alert.last_checked_at else None,
    }


def create_alert(
    db: Session,
    topic: str,
    place: str = "",
    min_magnitude: float | None = None,
    interval_minutes: int | None = None,
    satellite: str = "",
) -> WorldAlert:
    """Lanza ValueError con un mensaje apto para el usuario si los datos no sirven."""
    topic = topic.strip().lower()
    place = place.strip()
    if topic != SATELLITE_PASS and topic not in ALERT_TOPICS:
        raise ValueError(f"No se puede vigilar '{topic}'. Opciones: {', '.join([*ALERT_TOPICS, SATELLITE_PASS])}")
    if topic == SATELLITE_PASS:
        if not place:
            raise ValueError("Para avisar pasadas de un satélite indicá sobre qué lugar.")
    else:
        build_arguments(TOPICS[topic], place, MAX_ROWS)  # valida que el lugar esté si el tema lo exige
    if topic != "earthquakes":
        min_magnitude = None
    elif min_magnitude is not None:
        min_magnitude = max(2.5, min(float(min_magnitude), 10))

    alert = WorldAlert(
        topic=topic,
        place=place,
        min_magnitude=min_magnitude,
        satellite=satellite.strip() if topic == SATELLITE_PASS else "",
        interval_minutes=max(MIN_INTERVAL_MINUTES, int(interval_minutes or DEFAULT_INTERVAL_MINUTES)),
    )
    db.add(alert)
    db.commit()
    db.refresh(alert)
    return alert


def list_alerts(db: Session) -> list[WorldAlert]:
    return db.query(WorldAlert).order_by(WorldAlert.id).all()


def delete_alert(db: Session, alert_id: int) -> bool:
    alert = db.get(WorldAlert, alert_id)
    if alert is None:
        return False
    db.delete(alert)
    db.commit()
    return True


def _check_rows(alert: WorldAlert, client: GodsEyeClient) -> list[str]:
    topic = TOPICS[alert.topic]
    arguments = build_arguments(topic, alert.place, MAX_ROWS)
    if alert.min_magnitude is not None:
        arguments["min_magnitude"] = alert.min_magnitude
    rows = client.call_tool(topic.tool, arguments).data.get(topic.rows_key) or []

    first_check = alert.seen_json is None
    seen: list[str] = json.loads(alert.seen_json) if alert.seen_json else []
    known = set(seen)
    new_rows = [row for row in rows if row_id(row) not in known]
    seen.extend(row_id(row) for row in new_rows)
    alert.seen_json = json.dumps(seen[-MAX_SEEN:])

    if first_check or not new_rows:
        return []
    listed = "; ".join(topic.describe(row) for row in new_rows[:MAX_ITEMS_PER_MESSAGE])
    extra = len(new_rows) - MAX_ITEMS_PER_MESSAGE
    if extra > 0:
        listed += f"; y {extra} más"
    return [f"🌍 Alerta — {describe(alert)}: {listed}"]


def _check_satellite_pass(alert: WorldAlert, client: GodsEyeClient, now: datetime) -> list[str]:
    arguments: dict = {"location": {"place": alert.place}}
    if alert.satellite:
        arguments["satellite"] = alert.satellite
    data = client.call_tool("next_satellite_pass", arguments).data
    next_pass = data.get("pass") or {}
    rise = next_pass.get("rise")
    if not rise:
        return []
    rise_at = datetime.fromisoformat(rise.replace("Z", "+00:00")).astimezone(timezone.utc).replace(tzinfo=None)

    seen: list[str] = json.loads(alert.seen_json) if alert.seen_json else []
    alert.seen_json = json.dumps(seen[-MAX_SEEN:])
    if rise in seen or not (now <= rise_at <= now + timedelta(minutes=PASS_LEAD_MINUTES)):
        return []
    seen.append(rise)
    alert.seen_json = json.dumps(seen[-MAX_SEEN:])

    local = rise_at.replace(tzinfo=timezone.utc).astimezone().strftime("%H:%M")
    visible = "visible a simple vista" if next_pass.get("visible") else "no visible a simple vista"
    return [
        f"🛰️ {data.get('satellite') or alert.satellite or 'La ISS'} pasa sobre {alert.place} a las {local}: "
        f"sale por el {next_pass.get('rise_direction', '?')}, altura máxima "
        f"{round(next_pass.get('max_elevation_deg') or 0)}°, {visible}."
    ]


def check_alert(alert: WorldAlert, client: GodsEyeClient, now: datetime | None = None) -> list[str]:
    """Revisa una alerta y devuelve los avisos a mostrar. Actualiza `alert`, no hace commit."""
    now = now or utcnow()
    alert.last_checked_at = now
    try:
        if alert.topic == SATELLITE_PASS:
            return _check_satellite_pass(alert, client, now)
        return _check_rows(alert, client)
    except GodsEyeError as exc:
        # Servicio caído o falta una clave: se reintenta en la próxima vuelta, sin avisar cada vez.
        logger.warning("No se pudo revisar la alerta %s (%s): %s", alert.id, describe(alert), exc)
        return []


def check_due_alerts(db: Session, client: GodsEyeClient, events: EventBus, now: datetime | None = None) -> int:
    """Revisa las alertas a las que ya les toca. Devuelve cuántos avisos generó."""
    now = now or utcnow()
    sent = 0
    for alert in list_alerts(db):
        due = alert.last_checked_at is None or now - alert.last_checked_at >= timedelta(
            minutes=alert.interval_minutes
        )
        if not due:
            continue
        messages = check_alert(alert, client, now)
        db.commit()
        for message in messages:
            notify(events, message)
            sent += 1
    return sent
