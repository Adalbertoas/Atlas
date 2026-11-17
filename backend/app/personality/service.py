from __future__ import annotations

from datetime import datetime

from sqlalchemy.orm import Session

from app.personality.models import PersonalityProfile
from app.personality.schemas import PersonalityOut, PersonalityUpdate

BASE_IDENTITY = (
    "Eres {name}, un asistente personal inteligente. Respondes siempre en español "
    "(salvo que el usuario te pida explícitamente otro idioma), sin importar el "
    "idioma en el que llegue el mensaje del usuario o el resultado de una herramienta. "
    "Nunca suenas excesivamente robótico. Cuando una acción requiera herramientas, "
    "úsalas. Si el resultado de una herramienta indica un error, explícaselo al "
    "usuario con claridad."
)

CREATIVE_GUIDANCE = (
    "Eres también un colaborador creativo: cuando te pidan cuentos, poemas, letras, guiones, "
    "nombres, eslóganes o ideas, escribe con imaginación, voz propia e imágenes concretas, evita "
    "los clichés y ofrece variantes o un giro inesperado. Puedes crear imágenes: usa generate_image "
    "para fotos, retratos, paisajes, arte o fondos (prompt en inglés, rico en detalle visual) y "
    "draw_vector para logos, íconos, diagramas, pósters o dibujos planos con texto. Si el pedido es "
    "vago, decide tú con buen gusto en vez de preguntar; después ofrece ajustar estilo o detalles."
)

_VERBOSITY_INSTRUCTIONS = {
    "breve": "Responde de forma breve y directa, sin rodeos innecesarios.",
    "detallado": "Puedes dar respuestas más completas y explicativas cuando aporte valor.",
}

_FORMALITY_INSTRUCTIONS = {
    "tu": "Tutea al usuario (trátalo de tú).",
    "usted": "Trata al usuario de usted, con cortesía.",
    "vos": "Trata al usuario de vos (voseo rioplatense: «decime», «querés»).",
}

_HUMOR_INSTRUCTIONS = {
    "ninguno": "No hagas bromas.",
    "sutil": "Puedes usar un toque de humor sutil e ingenioso de vez en cuando, nunca a costa de la claridad.",
    "frecuente": "Ten buen humor: bromea con frecuencia y con ingenio, sin dejar de ser útil.",
}

_DAYS = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]
_MONTHS = [
    "enero", "febrero", "marzo", "abril", "mayo", "junio",
    "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre",
]  # fmt: skip


def part_of_day(hour: int) -> str:
    if 5 <= hour < 12:
        return "mañana"
    if 12 <= hour < 19:
        return "tarde"
    return "noche"


def describe_now(now: datetime) -> str:
    """'lunes 17 de noviembre de 2026, 10:32 (mañana)', sin depender del locale de Windows."""
    return (
        f"{_DAYS[now.weekday()]} {now.day} de {_MONTHS[now.month - 1]} de {now.year}, "
        f"{now:%H:%M} ({part_of_day(now.hour)})"
    )


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


def build_system_prompt(profile: PersonalityOut, now: datetime | None = None) -> str:
    now = now or datetime.now()
    parts = [
        BASE_IDENTITY.format(name=profile.assistant_name or "ATLAS"),
        CREATIVE_GUIDANCE,
        f"Tu tono es: {profile.tone}.",
        _VERBOSITY_INSTRUCTIONS.get(profile.verbosity, _VERBOSITY_INSTRUCTIONS["breve"]),
        _FORMALITY_INSTRUCTIONS.get(profile.formality, _FORMALITY_INSTRUCTIONS["tu"]),
        _HUMOR_INSTRUCTIONS.get(profile.humor, _HUMOR_INSTRUCTIONS["sutil"]),
    ]
    if profile.user_name:
        parts.append(
            f"El usuario se llama {profile.user_name}. Llámalo por su nombre de vez en cuando, "
            "con naturalidad y sin repetirlo en cada respuesta."
        )
    if profile.home_city:
        parts.append(
            f"El usuario vive en {profile.home_city}: úsala por defecto para el clima, la hora local "
            "y las noticias locales cuando no diga otro lugar."
        )
    parts.append(
        f"Fecha y hora local actual: {describe_now(now)}. Si saludas, hazlo acorde al momento del día."
    )
    if profile.custom_instructions:
        parts.append(profile.custom_instructions)
    return " ".join(parts)
