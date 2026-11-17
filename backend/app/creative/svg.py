"""Dibujos vectoriales (SVG) hechos por Claude: logos, íconos, diagramas,
ilustraciones planas, pósters.

El SVG que escribe el modelo se sanea antes de mostrarlo o guardarlo: sin
scripts, sin manejadores de eventos y sin recursos externos. En el escritorio
se muestra dentro de <img>, que ya bloquea scripts, pero el archivo guardado
puede abrirse en un navegador, así que el saneado es obligatorio.
"""
from __future__ import annotations

import re
import xml.etree.ElementTree as ET

from app.ai.base import AIMessage, AIProvider

SVG_NS = "http://www.w3.org/2000/svg"
XLINK_NS = "http://www.w3.org/1999/xlink"
ET.register_namespace("", SVG_NS)
ET.register_namespace("xlink", XLINK_NS)

_FORBIDDEN_TAGS = {"script", "foreignobject", "iframe", "object", "embed", "audio", "video", "image", "a", "animate", "set", "animatemotion", "animatetransform", "handler", "listener"}
_SVG_BLOCK = re.compile(r"<svg\b.*?</svg>", re.IGNORECASE | re.DOTALL)
_EXTERNAL_URL = re.compile(r"url\(\s*['\"]?\s*(?!#)[^)]*\)|@import[^;]*;?|expression\s*\(", re.IGNORECASE)
MAX_SVG_BYTES = 400_000

DRAW_SYSTEM_PROMPT = (
    "Eres un ilustrador y diseñador gráfico experto en SVG. Respondes ÚNICAMENTE con un "
    "documento SVG completo y válido, sin explicaciones ni bloques de código markdown. "
    "Reglas: elemento raíz <svg xmlns=\"http://www.w3.org/2000/svg\"> con viewBox (por defecto "
    "\"0 0 1024 1024\" salvo que se pida otro formato) y width/height iguales al viewBox; "
    "nada de <script>, <image>, <foreignObject>, enlaces, fuentes externas ni recursos externos; "
    "el texto con font-family genérica (sans-serif, serif, monospace). "
    "Cuida la calidad: composición equilibrada, paleta armónica, degradados (<linearGradient>, "
    "<radialGradient>) y filtros sutiles cuando aporten, formas limpias con <path>, y un fondo "
    "definido salvo que se pida fondo transparente. Prefiere el detalle bien resuelto a la cantidad."
)


class SvgError(Exception):
    """El modelo no devolvió un SVG utilizable."""


def _local(name: str) -> str:
    return name.rsplit("}", 1)[-1].lower()


def extract_svg(text: str) -> str:
    match = _SVG_BLOCK.search(text or "")
    if not match:
        raise SvgError("La IA no devolvió un dibujo SVG. Intenta describirlo de otra forma.")
    return match.group(0)


def sanitize_svg(svg: str) -> str:
    """Devuelve el SVG sin nada ejecutable ni externo. Lanza SvgError si no es SVG válido."""
    if len(svg.encode("utf-8")) > MAX_SVG_BYTES:
        raise SvgError("El dibujo es demasiado grande.")
    if "<!DOCTYPE" in svg.upper() or "<!ENTITY" in svg.upper():
        raise SvgError("El SVG trae declaraciones no permitidas.")
    head = svg[: svg.find(">") + 1]
    if "xmlns=" not in head:
        svg = svg.replace("<svg", f'<svg xmlns="{SVG_NS}"', 1)
    if "xlink:" in svg and "xmlns:xlink" not in svg[: svg.find(">") + 1]:
        svg = svg.replace("<svg", f'<svg xmlns:xlink="{XLINK_NS}"', 1)
    try:
        root = ET.fromstring(svg)
    except ET.ParseError as exc:
        raise SvgError("El SVG generado está mal formado. Intenta de nuevo.") from exc
    if _local(root.tag) != "svg":
        raise SvgError("El documento no es un SVG.")

    def clean(element: ET.Element) -> None:
        for child in list(element):
            if _local(child.tag) in _FORBIDDEN_TAGS:
                element.remove(child)
                continue
            clean(child)
        for attr in list(element.attrib):
            name = _local(attr)
            value = element.attrib[attr]
            if name.startswith("on"):
                del element.attrib[attr]
            elif name == "href" and not value.strip().startswith("#"):
                del element.attrib[attr]
            elif name == "style" or "url(" in value.lower():
                cleaned = _EXTERNAL_URL.sub(lambda m: m.group(0) if m.group(0).lower().startswith("url(#") else "none", value)
                element.attrib[attr] = cleaned
        if _local(element.tag) == "style" and element.text:
            element.text = _EXTERNAL_URL.sub("none", element.text)

    clean(root)
    if "viewBox" not in root.attrib:
        width, height = root.attrib.get("width", "1024"), root.attrib.get("height", "1024")
        root.attrib["viewBox"] = f"0 0 {re.sub(r'[^0-9.]', '', width) or 1024} {re.sub(r'[^0-9.]', '', height) or 1024}"
    return ET.tostring(root, encoding="unicode")


def svg_size(svg: str) -> tuple[int, int]:
    match = re.search(r'viewBox="\s*[-\d.]+[\s,]+[-\d.]+[\s,]+([\d.]+)[\s,]+([\d.]+)', svg)
    if not match:
        return 1024, 1024
    return round(float(match.group(1))), round(float(match.group(2)))


def draw(provider: AIProvider, description: str, aspect: str | None = None) -> str:
    description = (description or "").strip()
    if len(description) < 3:
        raise SvgError("Describe lo que quieres que dibuje.")
    formats = {"horizontal": "1536 1024", "vertical": "1024 1536"}
    hint = f" Formato: viewBox=\"0 0 {formats[aspect]}\"." if aspect in formats else ""
    response = provider.chat(
        [AIMessage(role="system", content=DRAW_SYSTEM_PROMPT), AIMessage(role="user", content=f"Dibuja: {description}.{hint}")]
    )
    return sanitize_svg(extract_svg(response.text or ""))
