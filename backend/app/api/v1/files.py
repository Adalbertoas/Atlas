from __future__ import annotations

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from app.core import outputs

router = APIRouter(prefix="/files", tags=["files"])


@router.get("/{name}")
def download(name: str) -> FileResponse:
    """Descarga un archivo generado por ATLAS (ej. el Excel de una factura)."""
    path = outputs.resolve(name)
    if path is None:
        raise HTTPException(status_code=404, detail="Ese archivo ya no existe en Documentos\\ATLAS.")
    return FileResponse(path, media_type=outputs.describe(path).mime_type, filename=path.name)
