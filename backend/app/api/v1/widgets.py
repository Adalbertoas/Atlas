"""Datos para los widgets del escritorio (panel «Hoy»): clima y titulares.

Directo, sin pasar por la IA: se refrescan solos cada pocos minutos sin gastar tokens.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.deps import get_db_session
from app.config import get_settings
from app.everyday import news, weather
from app.tools.base import ToolContext
from app.tools.everyday.everyday_tools import default_city
from app.web.client import WebError

router = APIRouter(prefix="/widgets", tags=["widgets"])


def _require_web() -> None:
    if not get_settings().web_enabled:
        raise HTTPException(status_code=403, detail="El acceso a internet está desactivado (WEB_ENABLED=false).")


@router.get("/weather")
def get_weather(place: str = "", days: int = 4, db: Session = Depends(get_db_session)) -> dict:
    _require_web()
    place = place.strip() or default_city(ToolContext(db=db))
    if not place:
        raise HTTPException(status_code=404, detail="Configura tu ciudad en Configuración → Personalidad.")
    try:
        return weather.get_weather(place, days).to_dict()
    except WebError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.get("/news")
def get_news(q: str = "", limit: int = 6) -> list[dict]:
    _require_web()
    try:
        return [h.to_dict() for h in news.get_news(q, limit)]
    except WebError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
