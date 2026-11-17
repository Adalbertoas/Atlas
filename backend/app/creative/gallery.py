"""Galería de creaciones: cada imagen se guarda como archivo en la carpeta de
creaciones (por defecto Imágenes\\ATLAS) y un index.json lleva sus datos
(prompt, motor, fecha). El usuario puede abrir la carpeta y usar los archivos
libremente; borrar un archivo a mano solo lo saca de la galería.
"""
from __future__ import annotations

import json
import os
import re
import threading
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

from app.config import get_settings

_EXTENSIONS = {"image/png": ".png", "image/jpeg": ".jpg", "image/webp": ".webp", "image/svg+xml": ".svg"}
_lock = threading.Lock()
_ID = re.compile(r"^[0-9a-f]{32}$")


@dataclass
class Creation:
    id: str
    file: str
    mime_type: str
    engine: str
    prompt: str
    width: int
    height: int
    created_at: str


def _pictures_dir() -> Path:
    """Carpeta Imágenes real del usuario (en Windows puede estar movida a otro disco)."""
    if os.name == "nt":
        try:
            import ctypes

            buffer = ctypes.create_unicode_buffer(260)
            if ctypes.windll.shell32.SHGetFolderPathW(None, 0x27, None, 0, buffer) == 0 and buffer.value:  # CSIDL_MYPICTURES
                return Path(buffer.value)
        except (OSError, AttributeError):
            pass
    return Path.home() / "Pictures"


def creations_dir() -> Path:
    configured = get_settings().creative_dir.strip()
    folder = Path(configured).expanduser() if configured else _pictures_dir() / "ATLAS"
    folder.mkdir(parents=True, exist_ok=True)
    return folder


def _index_path() -> Path:
    return creations_dir() / "index.json"


def _load() -> list[dict]:
    try:
        data = json.loads(_index_path().read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []
    except (OSError, ValueError):
        return []


def _store(items: list[dict]) -> None:
    path = _index_path()
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(items, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(path)


def _slug(text: str) -> str:
    words = re.sub(r"[^\w\s-]", "", text.lower()).split()[:6]
    return "-".join(words)[:48] or "creacion"


def save(data: bytes, mime_type: str, engine: str, prompt: str, width: int, height: int) -> Creation:
    creation_id = uuid.uuid4().hex
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    filename = f"{stamp}-{_slug(prompt)}-{creation_id[:6]}{_EXTENSIONS.get(mime_type, '.bin')}"
    creation = Creation(
        id=creation_id, file=filename, mime_type=mime_type, engine=engine, prompt=prompt,
        width=width, height=height, created_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
    )
    with _lock:
        (creations_dir() / filename).write_bytes(data)
        items = _load()
        items.insert(0, asdict(creation))
        _store(items)
    return creation


def path_of(creation: Creation) -> Path:
    return creations_dir() / creation.file


def recent(limit: int = 24) -> list[Creation]:
    """Las últimas creaciones cuyo archivo todavía existe."""
    folder = creations_dir()
    result: list[Creation] = []
    for item in _load():
        try:
            creation = Creation(**item)
        except TypeError:
            continue
        if (folder / creation.file).is_file():
            result.append(creation)
        if len(result) >= limit:
            break
    return result


def read(creation: Creation) -> bytes:
    return path_of(creation).read_bytes()


def get(creation_id: str) -> Creation | None:
    if not _ID.match(creation_id):
        return None
    return next((c for c in recent(10_000) if c.id == creation_id), None)


def thumbnail(creation: Creation, size: int = 384) -> tuple[bytes, str]:
    """Miniatura JPEG para la galería (cacheada en .thumbs/). Los SVG ya son livianos: van tal cual."""
    if creation.mime_type == "image/svg+xml":
        return read(creation), creation.mime_type
    thumbs = creations_dir() / ".thumbs"
    target = thumbs / f"{creation.id}.jpg"
    if target.is_file():
        return target.read_bytes(), "image/jpeg"
    from io import BytesIO

    from PIL import Image

    with Image.open(path_of(creation)) as image:
        image = image.convert("RGB")
        image.thumbnail((size, size))
        buffer = BytesIO()
        image.save(buffer, "JPEG", quality=82)
    thumbs.mkdir(exist_ok=True)
    target.write_bytes(buffer.getvalue())
    return buffer.getvalue(), "image/jpeg"


def delete(creation_id: str) -> bool:
    if not _ID.match(creation_id):
        return False
    with _lock:
        items = _load()
        keep = [i for i in items if i.get("id") != creation_id]
        if len(keep) == len(items):
            return False
        for item in items:
            if item.get("id") == creation_id:
                target = creations_dir() / Path(str(item.get("file", ""))).name
                for path in (target, creations_dir() / ".thumbs" / f"{creation_id}.jpg"):
                    try:
                        path.unlink(missing_ok=True)
                    except OSError:
                        pass
        _store(keep)
    return True
