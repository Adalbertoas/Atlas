"""Ayudante de configuración de Google Calendar + Gmail (Fases 21 y 23).

Google no da un refresh_token con solo pedirlo: hay que pasar una vez por
una pantalla de consentimiento en el navegador. Este script hace ese paso
por vos: levanta un servidor local temporal para recibir el código de
autorización (flujo OAuth2 "instalada", redirect a localhost), lo cambia
por un refresh_token y te dice qué pegar en backend/.env.

Pide los scopes de Calendar y Gmail en la misma pasada: un solo
refresh_token cubre ambas integraciones (misma cuenta de Google, mismo
Client ID/Secret). Si ya tenías un refresh_token de antes de que existiera
Gmail (Fase 21 sola), hay que volver a correr este script — el token viejo
no incluye el scope nuevo y las tools de Gmail van a fallar con
GmailNotConfigured hasta que se reemplace.

Antes de correrlo:
  1. https://console.cloud.google.com → crear proyecto (o usar uno existente).
  2. "APIs & Services" → "Library" → habilitar "Google Calendar API" Y
     "Gmail API" (las dos, por separado).
  3. "APIs & Services" → "Credentials" → "Create credentials" →
     "OAuth client ID" → tipo "Desktop app".
  4. Copiá el Client ID y el Client Secret a GOOGLE_CLIENT_ID/
     GOOGLE_CLIENT_SECRET en backend/.env.
  5. En la pantalla de consentimiento, agregá los scopes de Calendar
     (.../auth/calendar.events) y Gmail (.../auth/gmail.readonly,
     .../auth/gmail.send) en "Datos que quieres acceder".
  6. Si la pantalla de consentimiento pide agregar "test users" (proyectos
     en modo "Testing"), agregá tu propia cuenta de Google ahí.

Uso, desde backend/:

    python scripts/google_calendar_setup.py
"""
from __future__ import annotations

import sys
import threading
import urllib.parse
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

# La consola de Windows usa cp1252 y revienta con acentos/emoji — mismo bug
# ya encontrado en desktop/run.py, mobile/serve.py y scripts/tuya_setup.py.
for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="replace")

import requests  # noqa: E402

from app.config import get_settings  # noqa: E402
from app.integrations.gmail import SCOPE as GMAIL_SCOPE  # noqa: E402
from app.integrations.google_calendar import SCOPE as CALENDAR_SCOPE  # noqa: E402

SCOPE = f"{CALENDAR_SCOPE} {GMAIL_SCOPE}"

_PORT = 8765
_REDIRECT_URI = f"http://localhost:{_PORT}/"
_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
_TOKEN_URL = "https://oauth2.googleapis.com/token"


class _CallbackHandler(BaseHTTPRequestHandler):
    """Atiende un solo request: el redirect de Google con ?code=... Guarda
    el código en el propio servidor (self.server.auth_code) para que main()
    lo lea después de que el hilo del servidor termine."""

    def do_GET(self) -> None:  # noqa: N802 (nombre fijado por BaseHTTPRequestHandler)
        query = urllib.parse.urlparse(self.path).query
        params = urllib.parse.parse_qs(query)
        self.server.auth_code = params.get("code", [None])[0]  # type: ignore[attr-defined]
        self.server.auth_error = params.get("error", [None])[0]  # type: ignore[attr-defined]

        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        message = "Listo, ya podés cerrar esta pestaña." if self.server.auth_code else "Algo falló, mirá la terminal."  # type: ignore[attr-defined]
        self.wfile.write(f"<html><body><p>{message}</p></body></html>".encode("utf-8"))

    def log_message(self, format: str, *args) -> None:  # noqa: A002
        pass  # silencia el log default de BaseHTTPRequestHandler (ruido, no aporta acá)


def main() -> int:
    settings = get_settings()
    if not settings.google_client_id or not settings.google_client_secret:
        print("✗ Faltan GOOGLE_CLIENT_ID y/o GOOGLE_CLIENT_SECRET en backend/.env.")
        print("  Ver el docstring de este script para los pasos en Google Cloud Console.")
        return 1

    auth_url = _AUTH_URL + "?" + urllib.parse.urlencode(
        {
            "client_id": settings.google_client_id,
            "redirect_uri": _REDIRECT_URI,
            "response_type": "code",
            "scope": SCOPE,
            "access_type": "offline",  # necesario para que Google devuelva refresh_token
            "prompt": "consent",  # fuerza a reemitir refresh_token aunque ya se haya autorizado antes
        }
    )

    server = HTTPServer(("localhost", _PORT), _CallbackHandler)
    server.timeout = 300
    thread = threading.Thread(target=server.handle_request, daemon=True)
    thread.start()

    print("Abriendo el navegador para el consentimiento de Google…")
    print(f"Si no se abre solo, entrá manualmente a:\n{auth_url}\n")
    print("Tenés 5 minutos para completarlo antes de que este script se cierre solo.\n")
    webbrowser.open(auth_url)

    thread.join(timeout=305)
    auth_code = getattr(server, "auth_code", None)
    auth_error = getattr(server, "auth_error", None)

    if auth_error:
        print(f"✗ Google devolvió un error: {auth_error}")
        return 1
    if not auth_code:
        print("✗ No llegó ningún código de autorización (¿timeout o se cerró la pestaña antes de tiempo?).")
        return 1

    print("Código recibido, cambiándolo por tokens…")
    response = requests.post(
        _TOKEN_URL,
        data={
            "client_id": settings.google_client_id,
            "client_secret": settings.google_client_secret,
            "code": auth_code,
            "grant_type": "authorization_code",
            "redirect_uri": _REDIRECT_URI,
        },
        timeout=10,
    )
    if response.status_code != 200:
        print(f"✗ Google rechazó el intercambio ({response.status_code}): {response.text}")
        return 1

    refresh_token = response.json().get("refresh_token")
    if not refresh_token:
        print(
            "✗ Google no devolvió refresh_token. Si ya habías autorizado esta app antes, "
            "revocá el acceso en https://myaccount.google.com/permissions y volvé a correr "
            "este script — 'prompt=consent' debería evitarlo, pero es la causa más común."
        )
        return 1

    print("\n✓ Listo. Agregá esta línea a backend/.env:\n")
    print(f"GOOGLE_REFRESH_TOKEN={refresh_token}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
