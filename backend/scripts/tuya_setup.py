"""Ayudante de configuración de Tuya (Fase 12).

El dato más molesto de conseguir en la consola de Tuya es el **UID** de la
cuenta de la app vinculada: está escondido en "Devices > Link App Account"
y no siempre se muestra completo. Este script lo busca solo, prueba las
credenciales y lista los dispositivos que ATLAS podrá ver.

Uso, desde backend/ y con TUYA_ACCESS_ID/TUYA_ACCESS_SECRET ya puestos en
.env (el UID todavía no hace falta):

    python scripts/tuya_setup.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

# La consola de Windows usa cp1252 y revienta con acentos/emoji — mismo bug
# ya encontrado en desktop/run.py y mobile/serve.py.
for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="replace")

from app.config import get_settings  # noqa: E402
from app.smart_home.tuya_provider import TUYA_ENDPOINTS  # noqa: E402

# Esquemas posibles de la app vinculada. Tuya no expone "¿cuál usé?", así
# que se prueban todos: las apps de marca blanca (Mercury Smart incluida)
# suelen quedar bajo el esquema de Smart Life o el de Tuya.
APP_SCHEMAS = ("smartlife", "tuyaSmart")


def main() -> int:
    settings = get_settings()
    access_id = settings.tuya_access_id
    access_secret = settings.tuya_access_secret

    if not access_id or not access_secret:
        print("✗ Falta TUYA_ACCESS_ID y/o TUYA_ACCESS_SECRET en backend/.env.")
        print("  Sacalos de iot.tuya.com → tu proyecto Cloud → 'Overview' → Authorization Key.")
        return 1

    from tuya_connector import TuyaOpenAPI

    endpoint = settings.tuya_endpoint
    print(f"Probando credenciales contra {endpoint} …")

    api = TuyaOpenAPI(endpoint, access_id, access_secret)
    try:
        api.connect()
    except Exception as exc:  # noqa: BLE001
        print(f"✗ No se pudo conectar: {exc!r}")
        _print_endpoint_hint(endpoint)
        return 1

    if not api.is_connect():
        print("✗ Las credenciales fueron rechazadas.")
        _print_endpoint_hint(endpoint)
        return 1
    print("✓ Credenciales válidas.\n")

    # --- Buscar el UID de la cuenta vinculada ---
    uid = settings.tuya_uid
    if uid:
        print(f"Usando el TUYA_UID que ya está en .env: {uid}\n")
    else:
        print("Buscando cuentas de app vinculadas al proyecto…")
        for schema in APP_SCHEMAS:
            response = api.get(f"/v1.0/apps/{schema}/users", {"page_no": 1, "page_size": 100})
            users = (response.get("result") or {}).get("records") or []
            if users:
                uid = users[0]["uid"]
                print(f"✓ Cuenta encontrada bajo el esquema '{schema}'.")
                print(f"\n  >>> Poné esto en backend/.env:  TUYA_UID={uid}\n")
                break
        else:
            print("✗ No se encontró ninguna cuenta de app vinculada.")
            print("  En iot.tuya.com → tu proyecto → pestaña 'Devices' → 'Link App Account'")
            print("  → 'Add App Account' y escaneá el QR con la app Mercury Smart / Tuya Smart.")
            return 1

    # --- Listar dispositivos ---
    print("Dispositivos que ATLAS podrá ver:")
    response = api.get(f"/v1.0/users/{uid}/devices", {"page_no": 0, "page_size": 100})
    if not response.get("success"):
        print(f"✗ Error listando dispositivos: {response.get('msg', response)}")
        return 1

    devices = response.get("result") or []
    if not devices:
        print("  (ninguno — ¿la cuenta vinculada es la que tiene tus dispositivos?)")
        return 1

    for device in devices:
        online = "en línea" if device.get("online") else "desconectado"
        print(f"  · {device.get('name')}  [{device.get('category')}]  {online}")
        print(f"      id: {device.get('id')}")

    print(f"\n✓ {len(devices)} dispositivo(s). Ya podés poner SMART_HOME_PROVIDER=tuya en .env.")
    return 0


def _print_endpoint_hint(current: str) -> None:
    others = [f"{name} → {url}" for name, url in TUYA_ENDPOINTS.items() if url != current]
    print("\n  Causa más común: el centro de datos equivocado. Tu proyecto vive en UNO solo.")
    print("  Probá cambiando TUYA_ENDPOINT en .env por alguno de estos:")
    for item in others:
        print(f"    {item}")


if __name__ == "__main__":
    raise SystemExit(main())
