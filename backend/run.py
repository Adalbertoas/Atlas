"""Punto de entrada de conveniencia: `python run.py` desde backend/.

Equivalente a `uvicorn app.main:app --reload`.
"""
from __future__ import annotations

from pathlib import Path

import uvicorn

CERT_PATH = Path(__file__).resolve().parent.parent / "certs" / "dev-cert.pem"
KEY_PATH = Path(__file__).resolve().parent.parent / "certs" / "dev-key.pem"

if __name__ == "__main__":
    # reload_dirs=["app"]: sin esto, uvicorn vigila TODO el directorio backend/,
    # incluido .venv — y pyttsx3 (TTS) escribe caché de comtypes ahí mismo,
    # provocando un reinicio del servidor a mitad de cada request de voz.
    #
    # host="0.0.0.0" (no "127.0.0.1"): bug real encontrado en vivo — con
    # 127.0.0.1 el backend rechaza CUALQUIER conexión que no venga de esta
    # misma PC, incluido el celular en la misma WiFi (mobile/, dashboard/,
    # y gestos por WebSocket necesitan alcanzarlo desde otro dispositivo).
    #
    # HTTPS opcional: si corriste scripts/generate_dev_cert.py, se usa ese
    # certificado (necesario para que el celular pueda usar cámara/micrófono
    # — los navegadores lo exigen). Si no existe, cae a HTTP plano, como
    # antes — no rompe el flujo de quien no necesita probar desde el celular.
    ssl_kwargs = {}
    if CERT_PATH.exists() and KEY_PATH.exists():
        ssl_kwargs = {"ssl_certfile": str(CERT_PATH), "ssl_keyfile": str(KEY_PATH)}
        print(f"HTTPS activo con {CERT_PATH}")

    uvicorn.run(
        "app.main:app", host="0.0.0.0", port=8000, reload=True, reload_dirs=["app"], **ssl_kwargs
    )
