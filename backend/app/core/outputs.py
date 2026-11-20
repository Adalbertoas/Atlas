"""Archivos que ATLAS genera para el usuario (Excel, etc.) en Documentos\\ATLAS.

El chat no manda los bytes en la respuesta: devuelve nombre y tamaño, y el
cliente los baja por GET /api/v1/files/{name} cuando el usuario pulsa
"Descargar". Solo se sirven archivos de esa carpeta (sin subcarpetas).
"""
from __future__ import annotations

import mimetypes
import os
from pathlib import Path

from app.config import get_settings
from app.tools.base import ToolFile

XLSX_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def _documents_dir() -> Path:
    """Carpeta Documentos real del usuario (en Windows puede estar movida a otro disco)."""
    if os.name == "nt":
        try:
            import ctypes

            buffer = ctypes.create_unicode_buffer(260)
            if ctypes.windll.shell32.SHGetFolderPathW(None, 0x05, None, 0, buffer) == 0 and buffer.value:  # CSIDL_PERSONAL
                return Path(buffer.value)
        except (OSError, AttributeError):
            pass
    return Path.home() / "Documents"


def output_dir() -> Path:
    configured = get_settings().output_dir.strip()
    return Path(configured).expanduser() if configured else _documents_dir() / "ATLAS"


def describe(path: Path) -> ToolFile:
    mime = XLSX_MIME if path.suffix.lower() == ".xlsx" else (mimetypes.guess_type(path.name)[0] or "application/octet-stream")
    return ToolFile(name=path.name, path=str(path), mime_type=mime, size=path.stat().st_size)


def resolve(name: str, directory: Path | None = None) -> Path | None:
    """Ruta del archivo `name` dentro de la carpeta de salida, o None si no
    existe o si el nombre intenta salir de ella (.., rutas, unidades)."""
    if not name or name != Path(name).name or name.startswith("~$"):
        return None
    base = (directory or output_dir()).resolve()
    target = (base / name).resolve()
    if target.parent != base or not target.is_file():
        return None
    return target
