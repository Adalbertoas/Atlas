from __future__ import annotations

from app.personality.schemas import PersonalityUpdate
from app.personality.service import build_system_prompt, get_profile, update_profile


def test_get_profile_creates_default_on_first_call(db_session):
    profile = get_profile(db_session)
    assert profile.verbosity == "breve"
    assert profile.tone

    # Segunda llamada reutiliza la misma fila, no crea otra.
    profile_again = get_profile(db_session)
    assert profile_again.tone == profile.tone


def test_update_profile_partial_update(db_session):
    get_profile(db_session)  # crea el default
    updated = update_profile(db_session, PersonalityUpdate(verbosity="detallado"))
    assert updated.verbosity == "detallado"
    assert updated.tone  # el tono no se tocó, sigue con su valor previo


def test_update_profile_rejects_invalid_verbosity():
    import pytest
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        PersonalityUpdate(verbosity="gritando")


def test_build_system_prompt_reflects_profile(db_session):
    profile = update_profile(db_session, PersonalityUpdate(custom_instructions="Llámame jefe."))
    prompt = build_system_prompt(profile)
    assert "Llámame jefe." in prompt
    assert profile.tone in prompt


def test_build_system_prompt_forces_spanish(db_session):
    # Bug real: sin esta instrucción explícita, el modelo a veces respondía
    # en inglés pese a que todo el resto del prompt está en español.
    profile = get_profile(db_session)
    prompt = build_system_prompt(profile)
    assert "español" in prompt.lower()
