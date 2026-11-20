"""Base del sistema de herramientas de ATLAS (sección 4 del prompt maestro).

Cada Tool declara: nombre, descripción, parámetros (JSON Schema), permiso
requerido (RiskLevel) y su ejecución. execute() nunca debe lanzar excepciones
sin capturar hacia el llamador: siempre devuelve un ToolResult, incluso en
error, para que el Orchestrator pueda responder con naturalidad.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy.orm import Session

from app.ai.base import ToolSchema
from app.security.permissions import RiskLevel


@dataclass
class ToolContext:
    """Dependencias disponibles para una tool durante su ejecución."""

    db: Session
    user: str = "local_user"


@dataclass
class ToolImage:
    """Imagen que una tool devuelve para mostrarle al usuario (no va al modelo)."""

    mime_type: str
    data: str  # base64


@dataclass
class ToolFile:
    """Archivo que una tool generó (ej. un Excel): el chat ofrece descargarlo.
    `path` es la ruta local; el cliente lo baja por GET /files/{name}."""

    name: str
    path: str
    mime_type: str
    size: int


@dataclass
class ToolResult:
    success: bool
    data: Any = None
    error: str | None = None
    images: list[ToolImage] = field(default_factory=list)
    files: list[ToolFile] = field(default_factory=list)

    def as_text(self) -> str:
        if self.success:
            return str(self.data)
        return f"Error: {self.error}"


class Tool(ABC):
    name: str
    description: str
    parameters: dict[str, Any]  # JSON Schema de los parámetros
    risk_level: RiskLevel

    def schema(self) -> ToolSchema:
        return ToolSchema(name=self.name, description=self.description, parameters=self.parameters)

    def human_description(self, params: dict) -> str:
        """Descripción legible para pedir confirmación al usuario. Las tools de
        riesgo medio/alto deberían sobreescribir esto con algo más específico."""
        return f"Ejecutar '{self.name}' con parámetros {params}"

    def resolve_risk_level(self, params: dict) -> RiskLevel:
        """Nivel de riesgo real de esta llamada. Por defecto es el `risk_level`
        estático de la clase; tools cuyo riesgo depende de los parámetros (ej.
        set_device_state: encender una luz es LOW_RISK, pero abrir una
        cerradura es CRITICAL — sección 5 del prompt maestro) sobreescriben
        este método en vez de usar un único risk_level fijo."""
        return self.risk_level

    @abstractmethod
    def execute(self, params: dict, context: ToolContext) -> ToolResult:
        raise NotImplementedError
