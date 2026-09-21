"""Modelos declarativos para capacidades de alto nivel (Skills)."""
from __future__ import annotations

from pydantic import BaseModel, Field

from app.security.permissions import RiskLevel


class SkillDefinition(BaseModel):
    id: str
    name: str
    description: str
    version: str = "1.0.0"
    enabled: bool = True
    required_tools: list[str] = Field(default_factory=list)
    instructions: str = ""
    risk_level: RiskLevel = RiskLevel.READ_ONLY
    tags: list[str] = Field(default_factory=list)
