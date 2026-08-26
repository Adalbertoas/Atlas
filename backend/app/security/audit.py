"""AuditLog: registro de auditoría de ATLAS (sección 17).

Registra quién ejecutó qué herramienta, cuándo, con qué resultado y con qué
nivel de riesgo. Nunca debe contener API keys, contraseñas ni tokens.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone

from sqlalchemy import DateTime, String, Text
from sqlalchemy.orm import Mapped, Session, mapped_column

from app.core.database import Base

# Claves que jamás deben persistirse en el log de auditoría, por si algún
# parámetro las trae por error.
_SENSITIVE_KEYS = {"api_key", "password", "token", "secret", "authorization"}


def _sanitize(params: dict) -> dict:
    clean = {}
    for key, value in params.items():
        if key.lower() in _SENSITIVE_KEYS:
            clean[key] = "***redacted***"
        else:
            clean[key] = value
    return clean


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user: Mapped[str] = mapped_column(String(120), default="local_user")
    tool_name: Mapped[str] = mapped_column(String(120))
    parameters_json: Mapped[str] = mapped_column(Text, default="{}")
    risk_level: Mapped[str] = mapped_column(String(20))
    result_summary: Mapped[str] = mapped_column(Text, default="")
    success: Mapped[bool] = mapped_column(default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc)
    )


def list_recent(db: Session, limit: int = 20) -> list[AuditLog]:
    """Últimas ejecuciones de tools — Fase 9, panel de "actividad reciente"
    del dashboard. Solo lectura, nunca expone los parámetros sensibles
    (ya saneados por _sanitize en write_audit)."""
    return db.query(AuditLog).order_by(AuditLog.created_at.desc()).limit(limit).all()


def write_audit(
    db: Session,
    *,
    tool_name: str,
    parameters: dict,
    risk_level: str,
    result_summary: str,
    success: bool,
    user: str = "local_user",
) -> AuditLog:
    entry = AuditLog(
        user=user,
        tool_name=tool_name,
        parameters_json=json.dumps(_sanitize(parameters), ensure_ascii=False),
        risk_level=risk_level,
        result_summary=result_summary[:2000],
        success=success,
    )
    db.add(entry)
    db.commit()
    db.refresh(entry)
    return entry
