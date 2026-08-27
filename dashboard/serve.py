"""Servidor estático mínimo para el dashboard de ATLAS.

Fase 9 lo dejó escuchando solo en 127.0.0.1: el dashboard se pensó como la
interfaz de la propia PC que corre el backend. Fase 16 lo abrió a la red
local, a pedido del usuario, para poder entrar desde otro dispositivo — un
segundo monitor, una tablet, otra computadora de la casa.

**HTTPS deja de ser opcional al hacerlo.** Mientras se servía desde
127.0.0.1, los navegadores lo trataban como "contexto seguro" por sí solos
y el micrófono del orbe funcionaba sin certificado. Desde cualquier otra
IP eso ya no aplica: sin HTTPS, `getUserMedia` queda bloqueado y se caen
el orbe de voz y el control por gestos. Por eso, si existe el certificado
de desarrollo (scripts/generate_dev_cert.py) se usa; si no, se avisa que
esas dos funciones no van a andar fuera de esta PC.

Sobre exponerlo a la red: el dashboard no da acceso a nada que la PWA móvil
no exponga ya — todo pasa por el mismo login con contraseña y token JWT del
backend. Aun así solo debería usarse en una red de confianza.
"""
from __future__ import annotations

import http.server
import socket
import ssl
import sys
from pathlib import Path

# Mismo bug de siempre con la consola de Windows (cp1252) — ver desktop/run.py.
for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="replace")

PORT = 5174
DIRECTORY = Path(__file__).resolve().parent
CERT_PATH = DIRECTORY.parent / "certs" / "dev-cert.pem"
KEY_PATH = DIRECTORY.parent / "certs" / "dev-key.pem"


SHARED_DIR = DIRECTORY.parent / "shared"


class Handler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, directory=str(DIRECTORY), **kwargs)

    def end_headers(self) -> None:
        """Sin caché: es un servidor de desarrollo y los archivos cambian
        todo el tiempo.

        Bug real que motivó esto: el navegador se quedó con un index.html
        viejo (sin type="module") y cargó el app.js nuevo (con `import`).
        El script moría con SyntaxError y la página quedaba dibujada pero
        con todos los botones muertos — sin ningún error visible salvo en
        la consola. SimpleHTTPRequestHandler solo manda Last-Modified, que
        los navegadores usan para cachear "heurísticamente" sin revalidar.
        """
        self.send_header("Cache-Control", "no-store, must-revalidate")
        super().end_headers()

    def translate_path(self, path: str) -> str:
        """Mapea /shared/* a la carpeta shared/ de la raíz del repo.

        El wake word del navegador es idéntico en el dashboard y en la PWA;
        tener dos copias garantizaría que se desincronicen (ya pasó al
        renombrar la palabra de activación). Se sirve una sola desde acá."""
        if path.startswith("/shared/"):
            relative = path[len("/shared/") :].split("?", 1)[0].split("#", 1)[0]
            # Sin '..' ni rutas absolutas: este servidor escucha en la red.
            safe = (SHARED_DIR / relative).resolve()
            if safe.is_relative_to(SHARED_DIR.resolve()):
                return str(safe)
        return super().translate_path(path)


def _local_ip() -> str:
    """IP de esta PC en la red local. Abrir un socket UDP no envía nada:
    solo fuerza al SO a elegir la interfaz de salida."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.connect(("8.8.8.8", 80))
        return sock.getsockname()[0]
    except OSError:
        return "127.0.0.1"
    finally:
        sock.close()


if __name__ == "__main__":
    ip = _local_ip()
    httpd = http.server.ThreadingHTTPServer(("0.0.0.0", PORT), Handler)

    scheme = "http"
    if CERT_PATH.exists() and KEY_PATH.exists():
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.load_cert_chain(certfile=str(CERT_PATH), keyfile=str(KEY_PATH))
        httpd.socket = context.wrap_socket(httpd.socket, server_side=True)
        scheme = "https"

    print("ATLAS dashboard sirviendo en:")
    print(f"  → Esta PC:                       {scheme}://127.0.0.1:{PORT}")
    print(f"  → Otro dispositivo (misma WiFi): {scheme}://{ip}:{PORT}")
    if scheme == "https":
        print(
            "\n  ⚠ Certificado autofirmado: la primera vez, el navegador va a avisar\n"
            "    que no es de confianza — elegí 'Avanzado' → 'Continuar de todas\n"
            "    formas'. Es tu propio certificado.\n"
            f"    Hacelo también una vez en https://{ip}:8000/api/v1/system/health\n"
            "    o el dashboard no va a poder hablar con el backend."
        )
    else:
        print(
            "\n  ⚠ Sin certificado: el micrófono y la cámara NO van a funcionar\n"
            "    desde otro dispositivo (los navegadores exigen HTTPS fuera de\n"
            "    localhost). Generá uno con: python scripts/generate_dev_cert.py"
        )
    print("\nPresioná Ctrl+C para detener.\n")

    with httpd:
        httpd.serve_forever()
