"""Genera el par de claves VAPID para Web Push (Fase 22).

A diferencia de Google Calendar/Tuya/etc., esto no necesita ninguna cuenta
externa: VAPID es un estándar (RFC 8292) que solo requiere un par de claves
EC (P-256) generado una vez. La pública va en el navegador (identifica a
ATLAS ante el servicio push de Chrome/Firefox/Edge), la privada firma los
envíos y nunca sale del backend.

Formato: base64 URL-safe sin padding, el mismo que usan
`PushManager.subscribe({ applicationServerKey })` en el navegador y
`pywebpush.webpush(vapid_private_key=...)` en el backend — ninguno de los
dos lados necesita convertir nada.

Uso, desde backend/:

    python scripts/generate_vapid_keys.py
"""
from __future__ import annotations

import base64
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="replace")

from cryptography.hazmat.primitives import serialization  # noqa: E402
from cryptography.hazmat.primitives.asymmetric import ec  # noqa: E402


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def main() -> int:
    private_key = ec.generate_private_key(ec.SECP256R1())
    public_key = private_key.public_key()

    # Punto EC sin comprimir (0x04 + X + Y, 65 bytes): es literalmente lo
    # que el navegador espera como `applicationServerKey`.
    public_bytes = public_key.public_bytes(
        encoding=serialization.Encoding.X962,
        format=serialization.PublicFormat.UncompressedPoint,
    )
    # Escalar privado crudo, 32 bytes: lo que pywebpush espera en
    # `vapid_private_key`.
    private_value = private_key.private_numbers().private_value.to_bytes(32, "big")

    print("✓ Par de claves VAPID generado. Agregá esto a backend/.env:\n")
    print(f"VAPID_PUBLIC_KEY={_b64url(public_bytes)}")
    print(f"VAPID_PRIVATE_KEY={_b64url(private_value)}")
    print(
        "\nY completá VAPID_CONTACT_EMAIL con un email real (lo exige el "
        "protocolo VAPID: es el contacto si el servicio push del navegador "
        "necesita avisar algo, ej. exceso de envíos)."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
