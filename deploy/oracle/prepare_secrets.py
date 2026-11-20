"""Prepara lo secreto para el servidor, a partir de backend/.env de la PC:

  deploy/oracle/secrets/server.env          configuración del backend en el servidor
  deploy/oracle/secrets/cloudflared/        config.yml + credenciales del túnel

y agrega al backend/.env de la PC lo que necesita el agente (AGENT_SERVER_URL y
AGENT_TOKEN, la misma clave que el servidor). secrets/ no se sube a git.

    python deploy/oracle/prepare_secrets.py
"""
from __future__ import annotations

import re
import secrets
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PC_ENV = ROOT / "backend" / ".env"
OUT = Path(__file__).resolve().parent / "secrets"
TUNNEL_CREDS = Path("D:/tools/cloudflared/atlas-tunnel.json")
PUBLIC_URL = "https://atlas.sirinetrd.com"

# Se copian tal cual de la PC (claves, contraseña, voz, preferencias).
COPY = [
    "AI_PROVIDER", "ANTHROPIC_API_KEY", "ANTHROPIC_MODEL", "OPENAI_API_KEY", "OPENAI_IMAGE_MODEL", "OPENAI_IMAGE_QUALITY",
    "IMAGE_DEFAULT_ENGINE", "CREATIVE_MODEL", "BRAVE_API_KEY", "WEB_ENABLED", "HOME_PLACE", "BRIEFING_TIME",
    "ATLAS_PASSWORD", "JWT_SECRET", "JWT_EXPIRE_MINUTES", "KOKORO_VOICE", "KOKORO_SPEED", "WHISPER_MODEL_SIZE",
    "VISION_PROVIDER", "SMART_HOME_PROVIDER", "SMART_HOME_URL", "SMART_HOME_TOKEN",
]
# Propias del servidor.
SERVER = {
    "APP_ENV": "production",
    "AUTH_ENABLED": "true",
    "DATABASE_URL": "sqlite:////data/atlas.db",
    "OUTPUT_DIR": "/data/outputs",
    "CREATIVE_DIR": "/data/creations",
    "STT_PROVIDER": "whisper",
    "TTS_PROVIDER": "kokoro",
    "KOKORO_CACHE_DIR": "/data/hf",
    "SPEAKER_MODEL_PATH": "/data/models/speaker/voxceleb_resnet34_LM.onnx",
    "SPEAKER_PROFILE_PATH": "/data/speaker_profile.json",
    "GODS_EYE_URL": "",  # la consola geoespacial es local de la PC
    "PC_TOOLS_MODE": "agent",
}


def read_env(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        match = re.match(r"^\s*([A-Z][A-Z0-9_]*)\s*=\s*(.*?)\s*$", line)
        if match:
            values[match.group(1)] = match.group(2)
    return values


def set_env_value(path: Path, name: str, value: str) -> None:
    lines = path.read_text(encoding="utf-8").splitlines()
    pattern = re.compile(rf"^\s*{name}\s*=")
    for i, line in enumerate(lines):
        if pattern.match(line):
            lines[i] = f"{name}={value}"
            break
    else:
        lines.append(f"{name}={value}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    pc = read_env(PC_ENV)
    if pc.get("AUTH_ENABLED", "").lower() != "true" or not pc.get("ATLAS_PASSWORD"):
        raise SystemExit("Activa AUTH_ENABLED=true y ATLAS_PASSWORD en backend/.env antes de publicar el servidor.")
    token = pc.get("AGENT_TOKEN") or secrets.token_urlsafe(32)

    OUT.mkdir(exist_ok=True)
    lines = ["# Generado por deploy/oracle/prepare_secrets.py: backend de ATLAS en el servidor."]
    lines += [f"{k}={pc[k]}" for k in COPY if k in pc]
    lines += [f"{k}={v}" for k, v in SERVER.items()]
    lines.append(f"AGENT_TOKEN={token}")
    (OUT / "server.env").write_text("\n".join(lines) + "\n", encoding="utf-8")

    tunnel = OUT / "cloudflared"
    tunnel.mkdir(exist_ok=True)
    shutil.copy2(Path(__file__).resolve().parent / "cloudflared-config.yml", tunnel / "config.yml")
    shutil.copy2(TUNNEL_CREDS, tunnel / "atlas-tunnel.json")

    # La PC (agente) usa la misma clave para conectarse al servidor.
    set_env_value(PC_ENV, "AGENT_SERVER_URL", PUBLIC_URL)
    set_env_value(PC_ENV, "AGENT_TOKEN", token)

    speaker = ROOT / ".cache" / "speaker" / "voxceleb_resnet34_LM.onnx"
    print(f"Listo: {OUT}")
    print(f"  server.env con {len(lines) - 1} valores; AGENT_TOKEN agregado también a backend/.env de la PC")
    print(f"  modelo de huella de voz local: {'sí, se sube' if speaker.exists() else 'no está (la verificación de voz queda apagada)'}")


if __name__ == "__main__":
    main()
