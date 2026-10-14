"""search_documents: busca texto DENTRO de los archivos (search_files solo mira el nombre).

Lee texto plano, Word (.docx, que es un zip con XML: no necesita librerías) y
PDF (con pypdf, si está instalado). Tiene topes de cantidad, tamaño y tiempo
para no colgar el proceso en carpetas enormes.
"""
from __future__ import annotations

import os
import re
import time
import zipfile
from pathlib import Path
from xml.etree import ElementTree

from app.security.permissions import RiskLevel
from app.tools.base import Tool, ToolContext, ToolResult

TEXT_EXTENSIONS = {
    ".txt", ".md", ".markdown", ".rst", ".csv", ".tsv", ".json", ".log", ".ini", ".cfg", ".yaml", ".yml",
    ".toml", ".xml", ".html", ".htm", ".py", ".js", ".ts", ".css", ".sql", ".bat", ".ps1", ".tex", ".srt",
}  # fmt: skip
SKIP_DIRS = {"node_modules", "__pycache__", ".git", ".venv", "venv", "appdata", "$recycle.bin", "site-packages"}
DEFAULT_FOLDERS = ["Documents", "Desktop", "Downloads"]

MAX_RESULTS = 15
MAX_FILES = 3000
MAX_TEXT_BYTES = 3 * 1024 * 1024
MAX_BINARY_BYTES = 25 * 1024 * 1024  # pdf y docx
MAX_PDF_PAGES = 60
TIME_BUDGET_SECONDS = 20
SNIPPET_RADIUS = 90

_WORD_NAMESPACE = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"


def _read_docx(path: Path) -> str:
    with zipfile.ZipFile(path) as archive:
        root = ElementTree.fromstring(archive.read("word/document.xml"))
    paragraphs = []
    for paragraph in root.iter(f"{_WORD_NAMESPACE}p"):
        paragraphs.append("".join(node.text or "" for node in paragraph.iter(f"{_WORD_NAMESPACE}t")))
    return "\n".join(paragraphs)


def _read_pdf(path: Path) -> str:
    from pypdf import PdfReader  # import perezoso: dependencia opcional

    reader = PdfReader(str(path))
    return "\n".join((page.extract_text() or "") for page in reader.pages[:MAX_PDF_PAGES])


def pdf_supported() -> bool:
    try:
        import pypdf  # noqa: F401
    except ImportError:
        return False
    return True


def read_document(path: Path) -> str | None:
    """Texto del archivo, o None si el tipo no se soporta o es demasiado grande."""
    suffix = path.suffix.lower()
    size = path.stat().st_size
    if suffix in TEXT_EXTENSIONS:
        if size > MAX_TEXT_BYTES:
            return None
        return path.read_text(encoding="utf-8", errors="ignore")
    if size > MAX_BINARY_BYTES:
        return None
    if suffix == ".docx":
        return _read_docx(path)
    if suffix == ".pdf":
        return _read_pdf(path)
    return None


def _snippet(text: str, position: int, length: int) -> str:
    start = max(0, position - SNIPPET_RADIUS)
    end = min(len(text), position + length + SNIPPET_RADIUS)
    fragment = re.sub(r"\s+", " ", text[start:end]).strip()
    return ("…" if start > 0 else "") + fragment + ("…" if end < len(text) else "")


class SearchDocumentsTool(Tool):
    name = "search_documents"
    description = (
        "Busca un texto dentro del contenido de los documentos del usuario (texto plano, Word .docx "
        "y PDF) y devuelve los archivos que lo contienen con un fragmento. Para buscar por nombre de "
        "archivo usá search_files."
    )
    parameters = {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "Texto a buscar dentro de los archivos."},
            "path": {
                "type": "string",
                "description": "Carpeta donde buscar. Por defecto: Documentos, Escritorio y Descargas.",
            },
        },
        "required": ["query"],
    }
    # Solo lee, pero los fragmentos encontrados pasan al proveedor de IA.
    risk_level = RiskLevel.LOW_RISK

    def execute(self, params: dict, context: ToolContext) -> ToolResult:
        query = str(params.get("query", "")).strip()
        if len(query) < 2:
            return ToolResult(success=False, error="El parámetro 'query' necesita al menos 2 caracteres.")

        if params.get("path"):
            try:
                roots = [Path(str(params["path"])).expanduser().resolve()]
            except Exception as exc:  # noqa: BLE001
                return ToolResult(success=False, error=f"Ruta inválida: {exc}")
            if not roots[0].is_dir():
                return ToolResult(success=False, error=f"'{roots[0]}' no existe o no es una carpeta.")
        else:
            roots = [Path.home() / name for name in DEFAULT_FOLDERS if (Path.home() / name).is_dir()]

        extensions = TEXT_EXTENSIONS | {".docx"} | ({".pdf"} if pdf_supported() else set())
        needle = query.lower()
        matches: list[dict] = []
        scanned = 0
        stopped_early = ""
        deadline = time.monotonic() + TIME_BUDGET_SECONDS

        for root in roots:
            for folder, subfolders, files in os.walk(root, onerror=lambda _error: None):
                subfolders[:] = [d for d in subfolders if d.lower() not in SKIP_DIRS and not d.startswith(".")]
                for name in files:
                    path = Path(folder) / name
                    if path.suffix.lower() not in extensions or name.startswith("~$"):
                        continue
                    if scanned >= MAX_FILES:
                        stopped_early = f"se revisaron los primeros {MAX_FILES} archivos"
                    elif time.monotonic() > deadline:
                        stopped_early = f"se cortó a los {TIME_BUDGET_SECONDS} segundos"
                    if stopped_early or len(matches) >= MAX_RESULTS:
                        break
                    scanned += 1
                    try:
                        text = read_document(path)
                    except Exception:  # noqa: BLE001 — archivo dañado, protegido o en uso: se saltea
                        continue
                    if not text:
                        continue
                    position = text.lower().find(needle)
                    if position >= 0:
                        matches.append(
                            {
                                "file": str(path),
                                "occurrences": text.lower().count(needle),
                                "snippet": _snippet(text, position, len(query)),
                            }
                        )
                if stopped_early or len(matches) >= MAX_RESULTS:
                    break
            if stopped_early or len(matches) >= MAX_RESULTS:
                break

        data: dict = {"query": query, "files_scanned": scanned, "matches": matches}
        if stopped_early:
            data["note"] = f"Búsqueda incompleta: {stopped_early}."
        elif len(matches) >= MAX_RESULTS:
            data["note"] = f"Se muestran los primeros {MAX_RESULTS} archivos; puede haber más."
        if not pdf_supported():
            data["pdf"] = "Los PDF no se revisaron: falta instalar pypdf (pip install pypdf)."
        return ToolResult(success=True, data=data)
