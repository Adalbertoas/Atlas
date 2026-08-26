"""Servidor estático mínimo para el dashboard (Fase 9) de ATLAS.

A diferencia de mobile/serve.py, este solo escucha en 127.0.0.1: el
dashboard es explícitamente para la PC que ya corre el backend, no para
otros dispositivos de la red (ver docs/architecture.md, sección del
dashboard). El micrófono para el orbe de voz funciona igual sin HTTPS
porque los navegadores tratan a 127.0.0.1/localhost como "contexto seguro"
por sí solos.
"""
from __future__ import annotations

import http.server
import sys
from pathlib import Path

# Mismo bug de siempre con la consola de Windows (cp1252) — ver desktop/run.py.
for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="replace")

PORT = 5174
DIRECTORY = Path(__file__).resolve().parent


class Handler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, directory=str(DIRECTORY), **kwargs)


if __name__ == "__main__":
    httpd = http.server.ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    print(f"ATLAS dashboard sirviendo en: http://127.0.0.1:{PORT}")
    print("Presioná Ctrl+C para detener.\n")
    with httpd:
        httpd.serve_forever()
