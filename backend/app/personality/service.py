from __future__ import annotations

from sqlalchemy.orm import Session

from app.personality.models import PersonalityProfile
from app.personality.schemas import PersonalityOut, PersonalityUpdate

BASE_IDENTITY = (
    "Eres ATLAS, un asistente personal inteligente. Respondes siempre en español "
    "(salvo que el usuario te pida explícitamente otro idioma), sin importar el "
    "idioma en el que llegue el mensaje del usuario o el resultado de una herramienta. "
    "Nunca suenas excesivamente robótico. Cuando una acción requiera herramientas, "
    "úsalas. Si el resultado de una herramienta indica un error, explícaselo al "
    "usuario con claridad."
)

_VERBOSITY_INSTRUCTIONS = {
    "breve": "Responde de forma breve y directa, sin rodeos innecesarios.",
    "detallado": "Puedes dar respuestas más completas y explicativas cuando aporte valor.",
}


def get_profile(db: Session) -> PersonalityOut:
    """Devuelve el perfil activo, creando el default la primera vez."""
    profile = db.query(PersonalityProfile).first()
    if profile is None:
        profile = PersonalityProfile()
        db.add(profile)
        db.commit()
        db.refresh(profile)
    return PersonalityOut.model_validate(profile)


def update_profile(db: Session, data: PersonalityUpdate) -> PersonalityOut:
    profile = db.query(PersonalityProfile).first()
    if profile is None:
        profile = PersonalityProfile()
        db.add(profile)

    updates = data.model_dump(exclude_unset=True)
    for field, value in updates.items():
        setattr(profile, field, value)

    db.commit()
    db.refresh(profile)
    return PersonalityOut.model_validate(profile)


def build_system_prompt(profile: PersonalityOut) -> str:
    parts = [
        BASE_IDENTITY,
        f"Tu tono es: {profile.tone}.",
        _VERBOSITY_INSTRUCTIONS.get(profile.verbosity, _VERBOSITY_INSTRUCTIONS["breve"]),
    ]
    if profile.custom_instructions:
        parts.append(profile.custom_instructions)
    return " ".join(parts)
