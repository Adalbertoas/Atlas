"""Levanta todo ATLAS con un solo comando y lo detiene junto con Ctrl+C.

    python scripts/start_atlas.py              # backend, dashboard, móvil y Mundo
    python scripts/start_atlas.py --desktop    # además el cliente de escritorio
    python scripts/start_atlas.py --no-world --no-mobile

Cada servicio corre como proceso hijo; su salida se muestra con el nombre
del servicio adelante. Si uno se cae, se avisa y el resto sigue corriendo.
"""
from __future__ import annotations

import argparse
import os
import shutil
import socket
import subprocess
import sys
import threading
import time
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# Misma razón que desktop/run.py: la consola de Windows (cp1252) revienta con acentos.
for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)


@dataclass
class Service:
    name: str
    cwd: Path
    command: list[str]
    port: int | None = None  # puerto que abre al quedar listo; None si no abre ninguno
    url: str = ""


def build_services(args: argparse.Namespace) -> list[Service]:
    python = sys.executable
    services = [Service("backend", ROOT / "backend", [python, "run.py"], 8000, "API en el puerto 8000")]
    if not args.no_world:
        world_dir = ROOT / "integrations" / "gods-eye-view"
        npm = shutil.which("npm")
        if npm is None:
            print("[atlas] npm no está instalado: se omite Mundo (Gods Eye View).")
        elif not (world_dir / "node_modules").exists():
            print("[atlas] Mundo sin instalar: corré 'npm ci' en integrations/gods-eye-view. Se omite.")
        else:
            services.append(Service("mundo", world_dir, [npm, "run", "dev"], 4173, "http://127.0.0.1:4173"))
    services.append(
        Service("dashboard", ROOT / "dashboard", [python, "serve.py"], 5174, "http://127.0.0.1:5174")
    )
    if not args.no_mobile:
        services.append(Service("movil", ROOT / "mobile", [python, "serve.py"], 5173, "puerto 5173"))
    if args.desktop:
        services.append(Service("escritorio", ROOT / "desktop", [python, "run.py"]))
    return services


def port_in_use(port: int) -> bool:
    for family, host in ((socket.AF_INET, "127.0.0.1"), (socket.AF_INET6, "::1")):
        try:
            with socket.socket(family, socket.SOCK_STREAM) as sock:
                sock.settimeout(0.4)
                if sock.connect_ex((host, port)) == 0:
                    return True
        except OSError:
            continue
    return False


def pump_output(service: Service, process: subprocess.Popen) -> None:
    assert process.stdout is not None
    for line in process.stdout:
        print(f"[{service.name}] {line.rstrip()}", flush=True)


def stop(process: subprocess.Popen) -> None:
    if process.poll() is not None:
        return
    if sys.platform == "win32":
        # /T: también los nietos (uvicorn --reload y npm lanzan sus propios hijos).
        subprocess.run(
            ["taskkill", "/PID", str(process.pid), "/T", "/F"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )
    else:
        process.terminate()
    try:
        process.wait(timeout=10)
    except subprocess.TimeoutExpired:
        process.kill()


def main() -> int:
    parser = argparse.ArgumentParser(description="Levanta todos los servicios de ATLAS.")
    parser.add_argument("--desktop", action="store_true", help="incluir el cliente de escritorio (wake word)")
    parser.add_argument("--no-world", action="store_true", help="no levantar Gods Eye View")
    parser.add_argument("--no-mobile", action="store_true", help="no levantar la PWA móvil")
    args = parser.parse_args()

    running: list[tuple[Service, subprocess.Popen]] = []
    for service in build_services(args):
        if service.port and port_in_use(service.port):
            print(f"[atlas] {service.name}: el puerto {service.port} ya está en uso, se asume que ya corre.")
            continue
        process = subprocess.Popen(
            service.command,
            cwd=service.cwd,
            # Sin esto los hijos en Python retienen su salida en un buffer al no ver una consola.
            env={**os.environ, "PYTHONUNBUFFERED": "1", "PYTHONIOENCODING": "utf-8"},
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        threading.Thread(target=pump_output, args=(service, process), daemon=True).start()
        running.append((service, process))

    if not running:
        print("[atlas] No había nada para levantar.")
        return 0

    deadline = time.time() + 60
    pending = [service for service, _ in running if service.port]
    while pending and time.time() < deadline:
        pending = [service for service in pending if not port_in_use(service.port)]
        time.sleep(0.5)
    for service, _ in running:
        if service.port:
            state = "NO respondió a tiempo" if service in pending else f"listo — {service.url}"
            print(f"[atlas] {service.name}: {state}")
    print("[atlas] Ctrl+C para detener todo.")

    reported: set[str] = set()
    try:
        while True:
            time.sleep(1)
            for service, process in running:
                code = process.poll()
                if code is not None and service.name not in reported:
                    reported.add(service.name)
                    print(f"[atlas] {service.name} terminó (código {code}).")
            if len(reported) == len(running):
                return 1
    except KeyboardInterrupt:
        print("\n[atlas] Deteniendo…")
    finally:
        for _, process in running:
            stop(process)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
