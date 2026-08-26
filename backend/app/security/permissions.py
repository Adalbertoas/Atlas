"""Sistema de permisos de ATLAS (sección 5 del prompt maestro).

Cada herramienta declara un RiskLevel. El PermissionManager decide si una
ejecución puede correr directo o si primero necesita confirmación explícita
del usuario. Las acciones CRITICAL nunca se ejecutan automáticamente.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from enum import Enum


class RiskLevel(str, Enum):
    READ_ONLY = "READ_ONLY"
    LOW_RISK = "LOW_RISK"
    MEDIUM_RISK = "MEDIUM_RISK"
    HIGH_RISK = "HIGH_RISK"
    CRITICAL = "CRITICAL"


# Niveles que pueden ejecutarse sin pedir confirmación al usuario.
AUTO_APPROVE_LEVELS = {RiskLevel.READ_ONLY, RiskLevel.LOW_RISK}


@dataclass
class PendingConfirmation:
    """Una acción de riesgo medio+ esperando confirmación del usuario."""

    id: str
    tool_name: str
    parameters: dict
    risk_level: RiskLevel
    description: str
    conversation_id: str | None = None


@dataclass
class PermissionDecision:
    allowed: bool
    requires_confirmation: bool
    pending: PendingConfirmation | None = None
    reason: str = ""


class PermissionManager:
    """Evalúa si una tool puede ejecutarse y gestiona confirmaciones pendientes.

    Las confirmaciones pendientes se guardan en memoria de proceso: para V1
    (un solo usuario, un solo proceso) es suficiente. Si el sistema escala a
    múltiples workers, este store deberá moverse a Redis (ver .env.example).
    """

    def __init__(self) -> None:
        self._pending: dict[str, PendingConfirmation] = {}

    def evaluate(
        self,
        *,
        tool_name: str,
        risk_level: RiskLevel,
        parameters: dict,
        human_description: str,
        conversation_id: str | None = None,
    ) -> PermissionDecision:
        if risk_level in AUTO_APPROVE_LEVELS:
            return PermissionDecision(allowed=True, requires_confirmation=False)

        # MEDIUM_RISK, HIGH_RISK y CRITICAL siempre requieren confirmación
        # explícita del usuario (sección 5: "Nunca ejecutes automáticamente
        # acciones críticas").
        pending = PendingConfirmation(
            id=str(uuid.uuid4()),
            tool_name=tool_name,
            parameters=parameters,
            risk_level=risk_level,
            description=human_description,
            conversation_id=conversation_id,
        )
        self._pending[pending.id] = pending
        return PermissionDecision(
            allowed=False,
            requires_confirmation=True,
            pending=pending,
            reason=f"La acción '{tool_name}' es {risk_level.value} y requiere confirmación.",
        )

    def get_pending(self, confirmation_id: str) -> PendingConfirmation | None:
        return self._pending.get(confirmation_id)

    def resolve(self, confirmation_id: str) -> PendingConfirmation | None:
        """Consume (elimina) una confirmación pendiente, ya sea aprobada o no."""
        return self._pending.pop(confirmation_id, None)


# Instancia única a nivel de proceso, inyectada vía app.api.deps.
permission_manager = PermissionManager()
