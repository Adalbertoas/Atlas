from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_db_session
from app.config import get_settings
from app.security.audit import list_recent
from app.security.auth import get_current_user
from app.tools.system.get_system_info import collect_system_info

router = APIRouter(prefix="/system", tags=["system"])


@router.get("/health")
def health() -> dict:
    settings = get_settings()
    return {
        "status": "ok",
        "app_env": settings.app_env,
        "ai_provider": settings.ai_provider,
    }


@router.get("/status")
def status(_user: str = Depends(get_current_user)) -> dict:
    """Métricas de CPU/RAM/disco directas, sin pasar por la IA — para que el
    cliente de escritorio pueda sondear el estado del sistema cada pocos
    segundos sin gastar tokens ni esperar una respuesta de Claude."""
    return collect_system_info()


@router.get("/activity")
def activity(
    limit: int = 20,
    db: Session = Depends(get_db_session),
    _user: str = Depends(get_current_user),
) -> list[dict]:
    """Actividad reciente de ATLAS (Fase 9, panel del dashboard) — últimas
    ejecuciones de tools desde AuditLog (Fase 1), nunca antes expuesto vía API."""
    entries = list_recent(db, limit=limit)
    return [
        {
            "id": e.id,
            "tool_name": e.tool_name,
            "risk_level": e.risk_level,
            "success": e.success,
            "result_summary": e.result_summary,
            "created_at": e.created_at.isoformat(),
        }
        for e in entries
    ]
