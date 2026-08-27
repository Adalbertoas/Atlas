"""open_url: abre un link (http/https) en el navegador predeterminado.

Faltaba esta tool — visto en vivo: el usuario pidió "abrí Die with a
Smile" después de una búsqueda en YouTube, y el modelo terminó llamando a
open_file con la URL como si fuera una ruta local (rompía con "no existe
o no es un archivo", porque Path() la resolvía relativa al cwd del
backend). open_file es (a propósito) solo para archivos del disco —
esta tool cubre el caso de abrir resultados de búsqueda/música/web.

Solo http/https, nunca el string crudo a un shell: mismo espíritu que el
allowlist de open_application.py (sección 12 — nada de ejecución/apertura
arbitraria sin acotar el universo posible).
"""
from __future__ import annotations

import webbrowser
from urllib.parse import urlparse

from app.security.permissions import RiskLevel
from app.tools.base import Tool, ToolContext, ToolResult


class OpenUrlTool(Tool):
    name = "open_url"
    description = (
        "Abre un link (http/https) en el navegador predeterminado — por ejemplo, un "
        "video de YouTube, una canción de Spotify o un resultado de búsqueda web que "
        "ya se encontró antes en la conversación."
    )
    parameters = {
        "type": "object",
        "properties": {
            "url": {"type": "string", "description": "URL completa a abrir, ej. 'https://youtube.com/watch?v=...'."}
        },
        "required": ["url"],
    }
    # Solo abre una pestaña del navegador — no ejecuta ni modifica nada
    # local, por eso no exige confirmación (a diferencia de
    # open_application, que sí lanza procesos arbitrarios del allowlist).
    risk_level = RiskLevel.LOW_RISK

    def human_description(self, params: dict) -> str:
        return f"Abrir '{params.get('url', '?')}' en el navegador"

    def execute(self, params: dict, context: ToolContext) -> ToolResult:
        raw_url = str(params.get("url", "")).strip()
        if not raw_url:
            return ToolResult(success=False, error="El parámetro 'url' no puede estar vacío.")

        parsed = urlparse(raw_url)
        if parsed.scheme not in ("http", "https") or not parsed.netloc:
            return ToolResult(
                success=False,
                error="Solo puedo abrir URLs http/https completas (con esquema y dominio).",
            )

        try:
            opened = webbrowser.open(raw_url)
        except Exception as exc:  # noqa: BLE001
            return ToolResult(success=False, error=f"No pude abrir el link: {exc}")

        if not opened:
            return ToolResult(success=False, error="No se encontró un navegador para abrir el link.")
        return ToolResult(success=True, data=f"Abrí '{raw_url}' en el navegador.")
