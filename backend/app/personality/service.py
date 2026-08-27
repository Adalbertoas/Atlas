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
    "usuario con claridad. "
    "Cuando el usuario te pida buscar o poner algo puntual (una canción, un video, "
    "un dato), ve directo al grano: usa la herramienta, elegí vos mismo el resultado "
    "más relevante y actuá sobre ese (abrilo con open_url, respondé el dato, etc.) en "
    "la misma respuesta. No le devuelvas una lista de resultados para que elija ni le "
    "preguntes cuál quiere — eso es lo que haría un buscador, no un asistente. Solo "
    "pedile que elija si el pedido es realmente ambiguo (por ejemplo, dos canciones "
    "distintas con el mismo nombre) o si te lo pide explícitamente."
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
