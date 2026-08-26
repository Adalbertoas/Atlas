"""Configuración de logging de ATLAS.

Regla de seguridad (sección 17 del prompt maestro): nunca se deben loguear
secretos (API keys, tokens, contraseñas). Los módulos que registran datos
sensibles deben sanear los valores antes de pasarlos al logger.
"""
from __future__ import annotations

import logging
import sys


def configure_logging(level: str = "INFO") -> None:
    root = logging.getLogger()
    if root.handlers:
        # Ya configurado (ej. recarga de uvicorn) — no duplicar handlers.
        root.setLevel(level)
        return

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(
        logging.Formatter("%(asctime)s | %(levelname)-8s | %(name)s | %(message)s")
    )
    root.addHandler(handler)
    root.setLevel(level)

    # Librerías de terceros: bajar verbosidad por defecto.
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("anthropic").setLevel(logging.WARNING)
