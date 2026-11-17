"""Arma desktop/electron/bundle/ para el instalador: Python portable con las
dependencias del backend, el codigo del backend con su .env y los modelos.

    backend\\.venv\\Scripts\\python.exe desktop\\electron\\scripts\\stage-backend.py

El .env se copia tal cual (con las claves): el instalador resultante es
personal, no se comparte.
"""
from __future__ import annotations

import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
BACKEND = ROOT / "backend"
BUNDLE = ROOT / "desktop" / "electron" / "bundle"
HF_SOURCES = [ROOT / ".cache" / "huggingface" / "hub", Path.home() / ".cache" / "huggingface" / "hub"]
MODELS = ["models--hexgrad--Kokoro-82M", "models--Systran--faster-whisper-base"]


def copytree(src: Path, dst: Path, ignore=None) -> None:
    shutil.copytree(src, dst, ignore=ignore, dirs_exist_ok=True)


def main() -> int:
    if sys.prefix == sys.base_prefix:
        print("Correlo con el python del .venv del backend.")
        return 1
    if BUNDLE.exists():
        shutil.rmtree(BUNDLE)

    # Python base (sin documentacion ni cabeceras) + site-packages del venv encima.
    python = BUNDLE / "python"
    copytree(Path(sys.base_prefix), python, shutil.ignore_patterns("Doc", "include", "Scripts", "__pycache__", "test", "idlelib", "tcl"))
    site = python / "Lib" / "site-packages"
    copytree(BACKEND / ".venv" / "Lib" / "site-packages", site, shutil.ignore_patterns("__pycache__", "pytest*", "_pytest"))
    torch = site / "torch"
    shutil.rmtree(torch / "include", ignore_errors=True)
    for lib in (torch / "lib").glob("*.lib"):
        lib.unlink()

    backend = BUNDLE / "backend"
    copytree(BACKEND / "app", backend / "app", shutil.ignore_patterns("__pycache__"))
    shutil.copy2(BACKEND / ".env", backend / ".env")

    hub = BUNDLE / "models" / "huggingface" / "hub"
    for name in MODELS:
        source = next((base / name for base in HF_SOURCES if (base / name / "snapshots").exists() and any((base / name / "snapshots").iterdir())), None)
        if source is None:
            print(f"Falta el modelo {name} en la cache de Hugging Face.")
            return 1
        # Los snapshots de HF suelen ser enlaces; copytree los resuelve a archivos.
        copytree(source, hub / name)
    speaker = ROOT / ".cache" / "speaker" / "voxceleb_resnet34_LM.onnx"
    (BUNDLE / "models" / "speaker").mkdir(parents=True)
    shutil.copy2(speaker, BUNDLE / "models" / "speaker" / speaker.name)

    size = sum(f.stat().st_size for f in BUNDLE.rglob("*") if f.is_file())
    print(f"Bundle listo en {BUNDLE} ({size / 2**20:,.0f} MB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
