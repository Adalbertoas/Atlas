"""read_clipboard / write_clipboard: texto del portapapeles de Windows.

Vía la API de Win32 con ctypes (sin dependencias nuevas), mismo criterio que
control_media. Solo texto: imágenes y archivos copiados se informan como
"no hay texto".
"""
from __future__ import annotations

import ctypes
import time
from ctypes import wintypes

from app.security.permissions import RiskLevel
from app.tools.base import Tool, ToolContext, ToolResult

CF_UNICODETEXT = 13
GMEM_MOVEABLE = 0x0002
MAX_CLIPBOARD_CHARS = 6000  # lo leído va al contexto del modelo: se acota


def _win32():
    user32 = ctypes.WinDLL("user32", use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    # Sin estas firmas, en 64 bits los punteros se truncan a 32 y la lectura falla o crashea.
    user32.OpenClipboard.argtypes = [wintypes.HWND]
    user32.GetClipboardData.argtypes = [wintypes.UINT]
    user32.GetClipboardData.restype = wintypes.HANDLE
    user32.SetClipboardData.argtypes = [wintypes.UINT, wintypes.HANDLE]
    user32.SetClipboardData.restype = wintypes.HANDLE
    kernel32.GlobalLock.argtypes = [wintypes.HGLOBAL]
    kernel32.GlobalLock.restype = wintypes.LPVOID
    kernel32.GlobalUnlock.argtypes = [wintypes.HGLOBAL]
    kernel32.GlobalAlloc.argtypes = [wintypes.UINT, ctypes.c_size_t]
    kernel32.GlobalAlloc.restype = wintypes.HGLOBAL
    kernel32.GlobalFree.argtypes = [wintypes.HGLOBAL]
    return user32, kernel32


def _open_clipboard(user32) -> None:
    # Otro programa puede tenerlo abierto un instante: se reintenta brevemente.
    for _ in range(10):
        if user32.OpenClipboard(None):
            return
        time.sleep(0.05)
    raise OSError("El portapapeles está ocupado por otro programa.")


def read_clipboard_text() -> str | None:
    """Texto del portapapeles, o None si no contiene texto."""
    user32, kernel32 = _win32()
    _open_clipboard(user32)
    try:
        handle = user32.GetClipboardData(CF_UNICODETEXT)
        if not handle:
            return None
        pointer = kernel32.GlobalLock(handle)
        if not pointer:
            return None
        try:
            return ctypes.wstring_at(pointer)
        finally:
            kernel32.GlobalUnlock(handle)
    finally:
        user32.CloseClipboard()


def write_clipboard_text(text: str) -> None:
    user32, kernel32 = _win32()
    data = ctypes.create_unicode_buffer(text)
    size = ctypes.sizeof(data)
    handle = kernel32.GlobalAlloc(GMEM_MOVEABLE, size)
    if not handle:
        raise OSError("No hay memoria para copiar el texto.")
    pointer = kernel32.GlobalLock(handle)
    ctypes.memmove(pointer, data, size)
    kernel32.GlobalUnlock(handle)

    _open_clipboard(user32)
    try:
        user32.EmptyClipboard()
        if not user32.SetClipboardData(CF_UNICODETEXT, handle):
            kernel32.GlobalFree(handle)  # si falló, el bloque sigue siendo nuestro
            raise OSError("Windows rechazó el texto para el portapapeles.")
    finally:
        user32.CloseClipboard()


class ReadClipboardTool(Tool):
    name = "read_clipboard"
    description = (
        "Lee el texto que el usuario tiene copiado en el portapapeles. Usala cuando pida trabajar "
        "con 'lo que copié' (resumirlo, traducirlo, explicarlo)."
    )
    parameters = {"type": "object", "properties": {}, "required": []}
    # No modifica nada, pero el contenido pasa al proveedor de IA: no es un simple READ_ONLY.
    risk_level = RiskLevel.LOW_RISK

    def execute(self, params: dict, context: ToolContext) -> ToolResult:
        try:
            text = read_clipboard_text()
        except Exception as exc:  # noqa: BLE001
            return ToolResult(success=False, error=str(exc))
        if not text or not text.strip():
            return ToolResult(success=True, data="El portapapeles no tiene texto.")
        if len(text) > MAX_CLIPBOARD_CHARS:
            text = text[:MAX_CLIPBOARD_CHARS] + f"… (recortado; el original tiene {len(text)} caracteres)"
        return ToolResult(success=True, data=text)


class WriteClipboardTool(Tool):
    name = "write_clipboard"
    description = "Copia un texto al portapapeles, reemplazando lo que hubiera, para que el usuario lo pegue."
    parameters = {
        "type": "object",
        "properties": {"text": {"type": "string", "description": "Texto a copiar."}},
        "required": ["text"],
    }
    risk_level = RiskLevel.LOW_RISK

    def execute(self, params: dict, context: ToolContext) -> ToolResult:
        text = str(params.get("text") or "")
        if not text:
            return ToolResult(success=False, error="El parámetro 'text' no puede estar vacío.")
        try:
            write_clipboard_text(text)
        except Exception as exc:  # noqa: BLE001
            return ToolResult(success=False, error=str(exc))
        return ToolResult(success=True, data=f"Copiado al portapapeles ({len(text)} caracteres).")
