from __future__ import annotations

from fastapi import APIRouter

from app.tools.registry import tool_registry

router = APIRouter(prefix="/tools", tags=["tools"])


@router.get("")
def list_tools() -> list[dict]:
    """Solo lectura: expone qué herramientas existen y su nivel de riesgo (útil
    para debug y para el futuro dashboard)."""
    return [
        {
            "name": t.name,
            "description": t.description,
            "risk_level": t.risk_level.value,
            "parameters": t.parameters,
        }
        for t in tool_registry.list_tools()
    ]
