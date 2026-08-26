"""Genera un certificado HTTPS autofirmado para desarrollo en red local.

Necesario porque los navegadores (Safari/Chrome, en iOS y Android por igual)
exigen un "contexto seguro" (HTTPS o localhost) para dar acceso a la cámara
o el micrófono — sin esto, el celular no puede usar `getUserMedia` para el
control por gestos ni la voz. El certificado es válido solo para tu red
local (las IPs/hosts que le pases), no lo emite ninguna autoridad pública.

Uso:
    python scripts/generate_dev_cert.py 192.168.0.7

Genera certs/dev-cert.pem y certs/dev-key.pem (gitignorados) en la raíz del
proyecto, reutilizados por backend/run.py, mobile/serve.py y dashboard/serve.py.
"""
from __future__ import annotations

import datetime
import ipaddress
import sys
from pathlib import Path

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID

CERTS_DIR = Path(__file__).resolve().parent.parent / "certs"


def _san_entries(extra_hosts: list[str]) -> list[x509.GeneralName]:
    entries: list[x509.GeneralName] = [
        x509.DNSName("localhost"),
        x509.IPAddress(ipaddress.ip_address("127.0.0.1")),
    ]
    for host in extra_hosts:
        try:
            entries.append(x509.IPAddress(ipaddress.ip_address(host)))
        except ValueError:
            entries.append(x509.DNSName(host))
    return entries


def generate(extra_hosts: list[str]) -> None:
    CERTS_DIR.mkdir(exist_ok=True)
    key_path = CERTS_DIR / "dev-key.pem"
    cert_path = CERTS_DIR / "dev-cert.pem"

    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    subject = issuer = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "ATLAS Dev")])

    cert = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(issuer)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=1))
        .not_valid_after(datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(days=825))
        .add_extension(x509.SubjectAlternativeName(_san_entries(extra_hosts)), critical=False)
        .sign(key, hashes.SHA256())
    )

    key_path.write_bytes(
        key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.TraditionalOpenSSL,
            encryption_algorithm=serialization.NoEncryption(),
        )
    )
    cert_path.write_bytes(cert.public_bytes(serialization.Encoding.PEM))

    print(f"Certificado generado en: {cert_path}")
    print(f"Clave privada en:        {key_path}")
    print(f"Válido para: localhost, 127.0.0.1, {', '.join(extra_hosts)}")


if __name__ == "__main__":
    generate(sys.argv[1:])
