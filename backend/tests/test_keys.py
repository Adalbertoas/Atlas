"""Claves configurables desde la interfaz: validación, .env, aplicación en caliente y API."""
from __future__ import annotations

import httpx
import pytest

from app.config import get_settings
from app.core import keys

KEY = "sk-proj-" + "a1B2c3D4" * 5


@pytest.fixture()
def env(monkeypatch, tmp_path):
    path = tmp_path / ".env"
    path.write_text("AI_PROVIDER=anthropic\n# comentario\nOPENAI_API_KEY=\nBRAVE_API_KEY=xyz\n", encoding="utf-8")
    monkeypatch.setattr(keys, "ENV_PATH", path)
    settings = get_settings()
    monkeypatch.setattr(settings, "openai_api_key", "")
    monkeypatch.setattr(settings, "image_default_engine", "auto")
    return path


def _openai_answers(monkeypatch, status: int):
    seen = {}

    def fake_get(url, headers=None, **kwargs):
        seen["auth"] = headers["Authorization"]
        return httpx.Response(status, json={})

    monkeypatch.setattr(keys.httpx, "get", fake_get)
    return seen


@pytest.mark.parametrize("bad", ["", "hola", "sk-corta", f"{KEY}\nAI_PROVIDER=mock", f"{KEY} x", "pk-" + "a" * 30])
def test_rejects_malformed_keys(bad):
    with pytest.raises(keys.KeySettingError):
        keys.validate_openai_key(bad)


def test_write_env_value_replaces_or_appends_keeping_the_rest(env):
    keys.write_env_value("OPENAI_API_KEY", KEY)
    keys.write_env_value("IMAGE_DEFAULT_ENGINE", "openai")
    lines = env.read_text(encoding="utf-8").splitlines()
    assert lines == ["AI_PROVIDER=anthropic", "# comentario", f"OPENAI_API_KEY={KEY}", "BRAVE_API_KEY=xyz", "IMAGE_DEFAULT_ENGINE=openai"]
    with pytest.raises(keys.KeySettingError):
        keys.write_env_value("OPENAI_API_KEY", "a\nB=c")


def test_update_verifies_saves_and_applies_live(env, monkeypatch):
    seen = _openai_answers(monkeypatch, 200)
    result = keys.update(openai_api_key=f"  {KEY}  ")
    assert seen["auth"] == f"Bearer {KEY}"
    assert get_settings().openai_api_key == KEY  # en caliente, sin reiniciar
    assert f"OPENAI_API_KEY={KEY}" in env.read_text(encoding="utf-8")
    assert result["openai"] == {"configured": True, "masked": "••••c3D4"}
    assert KEY not in str(result)  # nunca se devuelve la clave


def test_rejected_key_is_not_saved(env, monkeypatch):
    _openai_answers(monkeypatch, 401)
    with pytest.raises(keys.KeySettingError, match="rechazó"):
        keys.update(openai_api_key=KEY)
    assert get_settings().openai_api_key == "" and KEY not in env.read_text(encoding="utf-8")


def test_unverifiable_key_is_saved_with_warning(env, monkeypatch):
    def offline(*args, **kwargs):
        raise httpx.ConnectError("sin red")

    monkeypatch.setattr(keys.httpx, "get", offline)
    result = keys.update(openai_api_key=KEY)
    assert get_settings().openai_api_key == KEY and "se guardó igual" in result["message"]


def test_remove_key_and_change_default_engine(env, monkeypatch):
    _openai_answers(monkeypatch, 200)
    keys.update(openai_api_key=KEY)
    result = keys.update(openai_api_key="", image_default_engine="pollinations")
    assert result["openai"]["configured"] is False and result["image_default_engine"] == "pollinations"
    text = env.read_text(encoding="utf-8")
    assert "OPENAI_API_KEY=\n" in text and "IMAGE_DEFAULT_ENGINE=pollinations" in text
    with pytest.raises(keys.KeySettingError):
        keys.update(image_default_engine="midjourney")


def test_keys_api(client, auth_headers, env, monkeypatch):
    _openai_answers(monkeypatch, 200)
    assert client.get("/api/v1/settings/keys", headers=auth_headers).json()["openai"]["configured"] is False
    saved = client.put("/api/v1/settings/keys", json={"openai_api_key": KEY}, headers=auth_headers)
    assert saved.status_code == 200 and saved.json()["openai"]["masked"] == "••••c3D4" and KEY not in saved.text
    engines = client.get("/api/v1/creative/engines", headers=auth_headers).json()
    assert "openai" in engines["available"] and engines["default"] == "openai"  # el estudio lo ve al instante
    bad = client.put("/api/v1/settings/keys", json={"openai_api_key": "hola"}, headers=auth_headers)
    assert bad.status_code == 422
    assert client.put("/api/v1/settings/keys", json={"openai_api_key": KEY}).status_code in (401, 403)
