"""Fixtures del smoke test E2E del dashboard.

Levanta backend + dashboard **dentro del propio proceso de test** (uvicorn y
el servidor estático corriendo en threads, no subprocesos) en vez de lanzar
`python run.py`/`python serve.py` como procesos aparte. Dos razones:

1. Puerto dinámico y libre: no pisa las instancias que ya puedas tener
   corriendo en 8000/5174 para uso normal, ni requiere pararlas primero.
2. Sin el bug de sockets huérfanos que ya documentó este proyecto
   (`--reload` de uvicorn en Windows puede dejar un proceso hijo pegado al
   puerto viejo) — acá no hay `--reload` ni procesos hijos, el server muere
   solo con el hilo apenas termina el proceso de pytest.

Importante: las variables de entorno que configuran ATLAS (DATABASE_URL,
AI_PROVIDER, etc.) se fijan **antes** de importar `app.main` — `Settings`
está cacheada con `@lru_cache` y el engine de la base se arma una sola vez
al importar `app.core.database`, así que corregirlas después no tendría
efecto. Por esto este archivo de tests debe correr en su propio proceso de
pytest, separado de `backend/tests/` (que ya fija sus propias variables al
importar su propio conftest.py) — mezclarlos en la misma sesión pisaría una
configuración con la otra.
"""
from __future__ import annotations

import importlib.util
import os
import socket
import sys
import threading
import time
from pathlib import Path

import pytest
import requests

DASHBOARD_DIR = Path(__file__).resolve().parent.parent
BACKEND_DIR = DASHBOARD_DIR.parent / "backend"
ATLAS_PASSWORD = "e2e-test-password"


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _wait_until_up(url: str, timeout: float = 15.0) -> None:
    deadline = time.monotonic() + timeout
    last_error: Exception | None = None
    while time.monotonic() < deadline:
        try:
            requests.get(url, timeout=1)
            return
        except requests.RequestException as exc:
            last_error = exc
            time.sleep(0.2)
    raise RuntimeError(f"{url} no respondió a tiempo") from last_error


@pytest.fixture(scope="session")
def backend_url(tmp_path_factory):
    # Todas las credenciales de integraciones externas vacías (mismo
    # criterio que backend/tests/conftest.py): sin esto, un import real
    # podría leer backend/.env y salir a internet de verdad.
    env = {
        "DATABASE_URL": f"sqlite:///{tmp_path_factory.mktemp('e2e') / 'atlas_e2e.db'}",
        "AI_PROVIDER": "mock",
        "STT_PROVIDER": "mock",
        "TTS_PROVIDER": "mock",
        "SMART_HOME_PROVIDER": "mock",
        "VISION_PROVIDER": "mock",
        "EMBEDDING_PROVIDER": "mock",
        "ATLAS_PASSWORD": ATLAS_PASSWORD,
        "BACKUP_ENABLED": "false",  # no ensuciar backups/ por un test
        "AUDD_API_TOKEN": "",
        "YOUTUBE_API_KEY": "",
        "SPOTIFY_CLIENT_ID": "",
        "SPOTIFY_CLIENT_SECRET": "",
        "TAVILY_API_KEY": "",
        "GOOGLE_CLIENT_ID": "",
        "GOOGLE_CLIENT_SECRET": "",
        "GOOGLE_REFRESH_TOKEN": "",
        "VAPID_PUBLIC_KEY": "",
        "VAPID_PRIVATE_KEY": "",
        "VAPID_CONTACT_EMAIL": "",
        "ATLAS_USER_NAME": "",
    }
    os.environ.update(env)

    sys.path.insert(0, str(BACKEND_DIR))
    import uvicorn

    from app.main import app  # import diferido: recién acá deben estar las env vars puestas

    port = _free_port()
    config = uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning")
    server = uvicorn.Server(config)

    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()

    base_url = f"http://127.0.0.1:{port}"
    _wait_until_up(f"{base_url}/api/v1/system/health")

    yield base_url

    server.should_exit = True
    thread.join(timeout=5)


@pytest.fixture(scope="session")
def dashboard_url():
    # Se reusa la clase Handler de dashboard/serve.py (mapeo de /shared/,
    # sin caché) en vez de reimplementar un servidor estático — es
    # seguro importarla como módulo: todo lo que abre el socket real vive
    # bajo `if __name__ == "__main__"`, nunca se ejecuta al importar.
    spec = importlib.util.spec_from_file_location("dashboard_serve", DASHBOARD_DIR / "serve.py")
    serve_module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(serve_module)

    import http.server

    port = _free_port()
    httpd = http.server.ThreadingHTTPServer(("127.0.0.1", port), serve_module.Handler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()

    base_url = f"http://127.0.0.1:{port}"
    _wait_until_up(f"{base_url}/index.html")

    yield base_url

    httpd.shutdown()
    thread.join(timeout=5)
