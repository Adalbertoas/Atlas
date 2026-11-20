"""Archivos que el usuario adjunta a un mensaje del chat (arrastrar, pegar o el clip).

Se validan y se dejan listos para mandarle al modelo: las imágenes se achican y
recodifican (una foto del celular o una captura 4K superan el límite de la API),
los PDF pasan tal cual. Nada se guarda en disco: viven solo durante ese pedido.
"""
from __future__ import annotations

import base64
import binascii
import io
import math
from dataclasses import dataclass

from app.ai.base import AIAttachment

IMAGE_TYPES = {"image/png", "image/jpeg", "image/webp", "image/gif"}
PDF_TYPE = "application/pdf"
MAX_ATTACHMENTS = 6
MAX_FILE_BYTES = 20 * 1024 * 1024
# La API de Anthropic acepta hasta 5 MB por imagen (en base64), pero reduce
# todo lo que pase de ~1.15 MP o 1568 px de lado: mandar más grande solo gasta.
MAX_VIEW_SIDE = 1568
MAX_VIEW_AREA = 1_150_000
MAX_IMAGE_B64 = 4_500_000
# Recortes de detalle (ver _detail_tiles).
MIN_DETAIL_SIDE = 1000
MAX_DETAIL_UPSCALE = 2.0
DETAIL_OVERLAP = 0.06
MAX_DETAILED_IMAGES = 3


class AttachmentError(ValueError):
    """Adjunto rechazado; el mensaje es apto para mostrar al usuario."""


@dataclass
class RawAttachment:
    name: str
    mime_type: str
    data: str  # base64


def _decode(item: RawAttachment) -> bytes:
    payload = item.data.split(",", 1)[1] if item.data.startswith("data:") else item.data
    try:
        raw = base64.b64decode(payload, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise AttachmentError(f"'{item.name or 'adjunto'}' no llegó bien codificado.") from exc
    if not raw:
        raise AttachmentError(f"'{item.name or 'adjunto'}' está vacío.")
    if len(raw) > MAX_FILE_BYTES:
        raise AttachmentError(f"'{item.name or 'adjunto'}' pesa más de {MAX_FILE_BYTES // (1024 * 1024)} MB.")
    return raw


def _open_image(raw: bytes, name: str):
    from PIL import Image, ImageOps, UnidentifiedImageError

    try:
        image = Image.open(io.BytesIO(raw))
        image.load()
    except (UnidentifiedImageError, OSError) as exc:
        raise AttachmentError(f"'{name}' no es una imagen que pueda leer.") from exc
    source_format = image.format  # exif_transpose devuelve una copia sin formato
    if getattr(image, "is_animated", False):
        image.seek(0)  # GIF animado: alcanza con el primer cuadro
    image = ImageOps.exif_transpose(image)  # fotos del celular: respeta la rotación
    return image, source_format == "PNG"


def _encode(image, prefer_png: bool) -> tuple[str, str]:
    """(mime_type, base64) por debajo del límite de peso de la API."""
    has_alpha = image.mode in ("RGBA", "LA") or (image.mode == "P" and "transparency" in image.info)
    # PNG conserva nítido el texto de capturas y tablas; si pesa demasiado, JPEG.
    candidates: list[tuple[str, dict]] = [("PNG", {"optimize": True})] if has_alpha or prefer_png else []
    candidates += [("JPEG", {"quality": q}) for q in (90, 80, 70)]
    for fmt, options in candidates:
        frame = image if fmt == "PNG" else image.convert("RGB")
        buffer = io.BytesIO()
        frame.save(buffer, format=fmt, **options)
        encoded = base64.b64encode(buffer.getvalue()).decode("ascii")
        if len(encoded) <= MAX_IMAGE_B64:
            return f"image/{fmt.lower()}", encoded
    # Último recurso: una imagen gigante y llena de ruido. Se achica a la mitad.
    smaller = image.convert("RGB")
    smaller.thumbnail((max(1, smaller.width // 2), max(1, smaller.height // 2)))
    buffer = io.BytesIO()
    smaller.save(buffer, format="JPEG", quality=75)
    return "image/jpeg", base64.b64encode(buffer.getvalue()).decode("ascii")


def _scaled(image, factor: float):
    from PIL import Image

    if abs(factor - 1) < 0.02:
        return image
    size = (max(1, round(image.width * factor)), max(1, round(image.height * factor)))
    return image.resize(size, Image.LANCZOS)


def _overview(image):
    """La imagen completa al tamaño que el modelo realmente ve (la API reduce
    todo lo que supere ~1.15 MP o 1568 px de lado)."""
    factor = min(1.0, MAX_VIEW_SIDE / max(image.size), math.sqrt(MAX_VIEW_AREA / (image.width * image.height)))
    return _scaled(image, factor)


def _detail_tiles(image) -> list[tuple[object, str]]:
    """Recortes ampliados para leer letra chica (RNC, NCF, montos de un ticket).
    Una foto de factura entera reducida a 1.15 MP deja los dígitos de pocos
    píxeles: el modelo confunde 7 con 2 o 3 con /. Cada recorte llega a la API
    sin reducir, con el texto hasta 2x más grande."""
    width, height = image.size
    if max(width, height) < MIN_DETAIL_SIDE:
        return []
    tall = height >= width
    long_side, short_side = (height, width) if tall else (width, height)
    ratio = long_side / short_side
    if ratio >= 1.5:
        # Franjas a lo largo del lado largo: ticket (vertical) o captura panorámica.
        count = 4 if ratio >= 3 else 3
        step = long_side / count
        overlap = long_side * DETAIL_OVERLAP
        boxes = []
        for i in range(count):
            start, end = max(0, i * step - overlap), min(long_side, (i + 1) * step + overlap)
            boxes.append((0, round(start), width, round(end)) if tall else (round(start), 0, round(end), height))
        where = "de arriba hacia abajo" if tall else "de izquierda a derecha"
        labels = [f"parte {i + 1} de {count}, {where}" for i in range(count)]
    else:
        # Foto casi cuadrada: cuadrícula de 2x2.
        half_w, half_h = width / 2, height / 2
        ow, oh = width * DETAIL_OVERLAP, height * DETAIL_OVERLAP
        boxes, labels = [], []
        for row, row_name in enumerate(("arriba", "abajo")):
            for col, col_name in enumerate(("izquierda", "derecha")):
                boxes.append((
                    round(max(0, col * half_w - ow)), round(max(0, row * half_h - oh)),
                    round(min(width, (col + 1) * half_w + ow)), round(min(height, (row + 1) * half_h + oh)),
                ))
                labels.append(f"cuadrante {row_name} a la {col_name}")
    tiles = []
    for box, label in zip(boxes, labels):
        tile = image.crop(box)
        area = tile.width * tile.height
        factor = min(MAX_DETAIL_UPSCALE, MAX_VIEW_SIDE / max(tile.size), math.sqrt(MAX_VIEW_AREA / area))
        tiles.append((_scaled(tile, factor), label))
    return tiles


def normalize_image_bytes(raw: bytes, name: str) -> tuple[str, str]:
    """(mime_type, base64) de la imagen completa, lista para la API."""
    image, prefer_png = _open_image(raw, name)
    return _encode(_overview(image), prefer_png)


def normalize(items: list[RawAttachment]) -> list[AIAttachment]:
    if len(items) > MAX_ATTACHMENTS:
        raise AttachmentError(f"Puedo recibir hasta {MAX_ATTACHMENTS} archivos por mensaje.")
    image_count = sum(1 for item in items if (item.mime_type or "").lower().strip() in IMAGE_TYPES)
    result: list[AIAttachment] = []
    for index, item in enumerate(items, start=1):
        name = (item.name or f"adjunto-{index}").strip()[:120]
        mime = (item.mime_type or "").lower().strip()
        raw = _decode(item)
        if mime in IMAGE_TYPES:
            image, prefer_png = _open_image(raw, name)
            mime, data = _encode(_overview(image), prefer_png)
            result.append(AIAttachment(kind="image", mime_type=mime, data=data, name=name))
            # Con muchas imágenes en un mismo mensaje no se agregan recortes:
            # cada uno cuesta lo mismo que una imagen más.
            if image_count <= MAX_DETAILED_IMAGES:
                for tile, label in _detail_tiles(image):
                    tile_mime, tile_data = _encode(tile, prefer_png)
                    result.append(AIAttachment(kind="image", mime_type=tile_mime, data=tile_data, name=name, detail=label))
        elif mime == PDF_TYPE:
            if not raw.startswith(b"%PDF"):
                raise AttachmentError(f"'{name}' no parece un PDF válido.")
            result.append(AIAttachment(kind="pdf", mime_type=PDF_TYPE, data=base64.b64encode(raw).decode("ascii"), name=name))
        else:
            raise AttachmentError(f"No puedo leer archivos de tipo '{mime or 'desconocido'}' ({name}). Probá con una imagen o un PDF.")
    return result
