from __future__ import annotations

from pydantic import BaseModel, ConfigDict, field_validator

VALID_VERBOSITY = {"breve", "detallado"}


class PersonalityUpdate(BaseModel):
    tone: str | None = None
    verbosity: str | None = None
    custom_instructions: str | None = None

    @field_validator("verbosity")
    @classmethod
    def check_verbosity(cls, v: str | None) -> str | None:
        if v is not None and v not in VALID_VERBOSITY:
            raise ValueError(f"verbosity debe ser una de {VALID_VERBOSITY}")
        return v


class PersonalityOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    tone: str
    verbosity: str
    custom_instructions: str
