"""Claves de servicios externos configurables desde la interfaz (por ahora OpenAI).

La clave se guarda en backend/.env (el mismo lugar donde se configura a mano)
y se aplica en caliente al objeto Settings en memoria: no hace falta reiniciar.
La API nunca devuelve la clave completa, solo si está configurada y sus
últimos 4 caracteres.
"""
from __future__ import annotations

import re
from pathlib import Path

import httpx

from app.config import get_settings

ENV_PATH = Path(__file__).resolve().parents[2] / ".env"

# Solo caracteres seguros: además de validar el formato, impide que un valor
# con saltos de línea o '=' agregue otras variables al .env.
_OPENAI_KEY = re.compile(r"^sk-[A-Za-z0-9_\-]{20,400}$")
IMAGE_ENGINES = ("auto", "openai", "pollinations")


class KeySettingError(ValueError):
    """Valor rechazado; el mensaje es apto para mostrar al usuario."""


def mask(key: str) -> str | None:
    return f"••••{key[-4:]}" if key else None


def validate_openai_key(key: str) -> str:
    key = (key or "").strip()
    if not _OPENAI_KEY.match(key):
        raise KeySettingError("Eso no parece una clave de OpenAI: debe empezar con «sk-» y no tener espacios.")
    return key


def verify_openai_key(key: str) -> tuple[bool | None, str]:
    """Prueba la clave contra OpenAI. (True, _) válida, (False, motivo) rechazada,
    (None, motivo) no se pudo comprobar (sin red, OpenAI caído)."""
    try:
        response = httpx.get("https://api.openai.com/v1/models", headers={"Authorization": f"Bearer {key}"}, timeout=15.0)
    except httpx.HTTPError:
        return None, "No pude contactar a OpenAI para comprobar la clave; se guardó igual."
    if response.status_code == 200:
        return True, "Clave de OpenAI verificada."
    if response.status_code in (401, 403):
        return False, "OpenAI rechazó la clave (inválida, revocada o sin permisos)."
    return None, f"OpenAI respondió HTTP {response.status_code}; no pude comprobar la clave, se guardó igual."


def write_env_value(name: str, value: str, path: Path | None = None) -> None:
    """Reemplaza (o agrega) NAME=value en el .env conservando el resto del archivo."""
    path = path or ENV_PATH
    if not re.fullmatch(r"[A-Z][A-Z0-9_]*", name) or any(c in value for c in "\r\n"):
        raise KeySettingError("Valor no permitido.")
    lines = path.read_text(encoding="utf-8").splitlines() if path.exists() else []
    line = f"{name}={value}"
    pattern = re.compile(rf"^\s*{re.escape(name)}\s*=")
    for index, current in enumerate(lines):
        if pattern.match(current):
            lines[index] = line
            break
    else:
        lines.append(line)
    tmp = path.with_suffix(".env.tmp")
    tmp.write_text("\n".join(lines) + "\n", encoding="utf-8")
    tmp.replace(path)


def status() -> dict:
    settings = get_settings()
    return {
        "openai": {"configured": bool(settings.openai_api_key), "masked": mask(settings.openai_api_key)},
        "image_default_engine": settings.image_default_engine or "auto",
        "env_path": str(ENV_PATH),
    }


def update(openai_api_key: str | None = None, image_default_engine: str | None = None, verify: bool = True) -> dict:
    """Aplica los cambios pedidos. openai_api_key="" quita la clave; None no la toca."""
    settings = get_settings()
    messages: list[str] = []
    if image_default_engine is not None:
        engine = image_default_engine.strip().lower()
        if engine not in IMAGE_ENGINES:
            raise KeySettingError("Motor por defecto desconocido.")
        write_env_value("IMAGE_DEFAULT_ENGINE", engine)
        settings.image_default_engine = engine
    if openai_api_key is not None:
        if openai_api_key.strip() == "":
            write_env_value("OPENAI_API_KEY", "")
            settings.openai_api_key = ""
            messages.append("Clave de OpenAI eliminada.")
        else:
            key = validate_openai_key(openai_api_key)
            if verify:
                ok, message = verify_openai_key(key)
                if ok is False:
                    raise KeySettingError(message)
                messages.append(message)
            write_env_value("OPENAI_API_KEY", key)
            settings.openai_api_key = key
    return {**status(), "message": " ".join(messages) or "Guardado."}
