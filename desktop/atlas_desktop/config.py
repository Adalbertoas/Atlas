"""Configuración del cliente de escritorio.

Cliente puro: no tiene lógica de negocio propia, solo habla con la API de
ATLAS (backend/). La URL es configurable por variable de entorno para poder
apuntar a un servidor en otra máquina de la red más adelante.
"""
from __future__ import annotations

import os
from pathlib import Path

try:
    from dotenv import load_dotenv

    load_dotenv(Path(__file__).resolve().parent.parent / ".env")
except ImportError:
    pass  # python-dotenv es opcional: sin él, se leen variables de entorno reales

# El backend sirve por HTTPS (certificado autofirmado, ver
# scripts/generate_dev_cert.py) cuando ese certificado existe — mismo criterio
# que backend/run.py para decidirlo. Si el cliente sigue apuntando a http://
# mientras el backend ya solo escucha en https://, el login falla en
# silencio (requests no puede ni conectar) y la ventana nunca aparece.
_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
_DEV_CERT_PATH = _REPO_ROOT / "certs" / "dev-cert.pem"
_DEFAULT_SCHEME = "https" if _DEV_CERT_PATH.exists() else "http"

ATLAS_API_URL = os.environ.get("ATLAS_API_URL", f"{_DEFAULT_SCHEME}://127.0.0.1:8000").rstrip("/")

# Certificado con el que validar esa conexión HTTPS local (en vez de
# desactivar la verificación TLS por completo). `requests` acepta pasarle
# la ruta de un certificado directamente en el parámetro `verify`.
ATLAS_CA_CERT: str | bool = str(_DEV_CERT_PATH) if _DEV_CERT_PATH.exists() else True

# Misma contraseña que ATLAS_PASSWORD en backend/.env — Fase 7: el cliente
# de escritorio dejó de ser anónimo, ahora se loguea igual que el móvil.
ATLAS_PASSWORD = os.environ.get("ATLAS_PASSWORD", "")
