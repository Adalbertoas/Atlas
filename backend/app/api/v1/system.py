from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_db_session
from app.config import get_settings
from app.security.audit import list_recent
from app.security.auth import get_current_user
from app.security.privacy import build_privacy_report
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
    segundos sin gastar tokens ni esperar una respuesta de Claude.

    Con el backend en un servidor (PC_TOOLS_MODE=agent) son los de la PC,
    que informa el agente; sin agente conectado, vacíos con pc_online=false."""
    if get_settings().pc_tools_mode == "agent":
        from app.agent.hub import agent_hub

        status = agent_hub.fresh_status()
        if status is None:
            return {"pc_online": False, "cpu_percent": None, "ram_percent": None}
        return {**status, "pc_online": True}
    return {**collect_system_info(), "pc_online": True}


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


@router.get("/privacy")
def privacy(_user: str = Depends(get_current_user)) -> dict:
    """Qué datos salen de esta PC y a dónde, según la configuración activa
    (panel Privacidad del dashboard). Ver app/security/privacy.py."""
    settings = get_settings()
    return {"auth_enabled": settings.auth_enabled, "flows": build_privacy_report(settings)}
