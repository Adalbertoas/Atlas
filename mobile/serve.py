"""Servidor estático mínimo para el cliente móvil (PWA) de ATLAS.

Sin build step, sin Node/npm — HTML/CSS/JS vanilla servidos tal cual, mismo
espíritu que evitar C#/.NET en el escritorio (Fase 4): menos piezas móviles.

Escucha en 0.0.0.0 para que un celular en la misma red WiFi pueda entrar
usando la IP local de esta PC (ej. http://192.168.1.50:5173).
"""
from __future__ import annotations

import http.server
import socket
import ssl
import sys
from pathlib import Path

# La consola de Windows suele usar cp1252, que no representa flechas/emoji —
# mismo bug ya encontrado en desktop/run.py. Se corrige igual acá.
for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="replace")

PORT = 5173
DIRECTORY = Path(__file__).resolve().parent
CERT_PATH = DIRECTORY.parent / "certs" / "dev-cert.pem"
KEY_PATH = DIRECTORY.parent / "certs" / "dev-key.pem"


class Handler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, directory=str(DIRECTORY), **kwargs)

    def end_headers(self) -> None:
        # Necesario para que el service worker pueda cachear/controlar la página.
        self.send_header("Service-Worker-Allowed", "/")
        super().end_headers()


def _local_ip() -> str:
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        return s.getsockname()[0]
    except OSError:
        return "127.0.0.1"
    finally:
        s.close()


if __name__ == "__main__":
    ip = _local_ip()
    httpd = http.server.ThreadingHTTPServer(("0.0.0.0", PORT), Handler)

    # HTTPS opcional (scripts/generate_dev_cert.py): necesario para que el
    # celular pueda usar la cámara (Gestos) o el micrófono — los navegadores
    # exigen un "contexto seguro". Si no hay certificado, cae a HTTP plano
    # (sirve igual para chat/dispositivos/etc, solo cámara/mic no andarían
    # desde el celular).
    scheme = "http"
    if CERT_PATH.exists() and KEY_PATH.exists():
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        ctx.load_cert_chain(certfile=str(CERT_PATH), keyfile=str(KEY_PATH))
        httpd.socket = ctx.wrap_socket(httpd.socket, server_side=True)
        scheme = "https"

    print("ATLAS móvil (PWA) sirviendo en:")
    print(f"  → Esta PC:        {scheme}://127.0.0.1:{PORT}")
    print(f"  → Desde tu celular (misma WiFi): {scheme}://{ip}:{PORT}")
    if scheme == "https":
        print(
            "  ⚠️ Certificado autofirmado: la primera vez, el navegador va a "
            "avisar que no es de confianza — elegí 'Visitar de todas formas' "
            "(o similar) para continuar. Es normal, es tu propio certificado."
        )
    print("Presioná Ctrl+C para detener.\n")

    with httpd:
        httpd.serve_forever()
