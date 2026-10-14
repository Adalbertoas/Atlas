from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.deps import get_db_session
from app.world import alerts
from app.world.state import world_view_state

router = APIRouter(prefix="/world", tags=["world"])


@router.get("/view")
def latest_world_view() -> dict:
    """Última vista que ATLAS pidió mostrar en Gods Eye View. El dashboard la
    consulta periódicamente y aplica la que todavía no mostró (compara `id`)."""
    update = world_view_state.latest()
    if update is None:
        return {"id": None}
    return {"id": update.id, "view": update.view, "url": update.url, "summary": update.summary}


@router.get("/alerts")
def list_world_alerts(db: Session = Depends(get_db_session)) -> list[dict]:
    return [alerts.to_dict(alert) for alert in alerts.list_alerts(db)]


@router.delete("/alerts/{alert_id}")
def delete_world_alert(alert_id: int, db: Session = Depends(get_db_session)) -> dict:
    if not alerts.delete_alert(db, alert_id):
        raise HTTPException(status_code=404, detail="Alerta no encontrada.")
    return {"deleted": True}
