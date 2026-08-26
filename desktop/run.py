"""Punto de entrada del cliente de escritorio: `python run.py` desde desktop/.

Requiere que el backend de ATLAS esté corriendo (ver backend/run.py).
"""
from __future__ import annotations

import sys
from pathlib import Path

# La consola de Windows suele usar cp1252 por defecto, que no puede
# representar muchos caracteres (acentos raros, texto transcrito por
# Whisper, etc.) — sin esto, un solo print/traceback con el carácter
# equivocado tira una UnicodeEncodeError que mata el hilo que lo llamó
# (pasó de verdad: mató el hilo de escucha del wake word en silencio).
for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="replace")

sys.path.insert(0, str(Path(__file__).resolve().parent))

from atlas_desktop.main import main  # noqa: E402

if __name__ == "__main__":
    main()
