from __future__ import annotations

from pydantic import BaseModel, ConfigDict, field_validator

VALID_VERBOSITY = {"breve", "detallado"}
VALID_FORMALITY = {"tu", "usted", "vos"}
VALID_HUMOR = {"ninguno", "sutil", "frecuente"}


def _one_of(value: str | None, valid: set[str], field: str) -> str | None:
    if value is not None and value not in valid:
        raise ValueError(f"{field} debe ser una de {sorted(valid)}")
    return value


class PersonalityUpdate(BaseModel):
    tone: str | None = None
    verbosity: str | None = None
    custom_instructions: str | None = None
    assistant_name: str | None = None
    user_name: str | None = None
    formality: str | None = None
    humor: str | None = None
    home_city: str | None = None

    @field_validator("verbosity")
    @classmethod
    def check_verbosity(cls, v: str | None) -> str | None:
        return _one_of(v, VALID_VERBOSITY, "verbosity")

    @field_validator("formality")
    @classmethod
    def check_formality(cls, v: str | None) -> str | None:
        return _one_of(v, VALID_FORMALITY, "formality")

    @field_validator("humor")
    @classmethod
    def check_humor(cls, v: str | None) -> str | None:
        return _one_of(v, VALID_HUMOR, "humor")

    @field_validator("assistant_name")
    @classmethod
    def check_assistant_name(cls, v: str | None) -> str | None:
        if v is None:
            return v
        v = v.strip()
        if not v or len(v) > 40:
            raise ValueError("El nombre del asistente debe tener entre 1 y 40 caracteres.")
        return v

    @field_validator("tone", "user_name", "home_city", "custom_instructions")
    @classmethod
    def strip_text(cls, v: str | None) -> str | None:
        return v.strip() if v is not None else v


class PersonalityOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    tone: str
    verbosity: str
    custom_instructions: str
    assistant_name: str = "ATLAS"
    user_name: str = ""
    formality: str = "tu"
    humor: str = "sutil"
    home_city: str = ""
