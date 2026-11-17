"""Tools creativas: imágenes (OpenAI / Pollinations) y dibujos vectoriales (Claude)."""
from __future__ import annotations

import base64

from app.creative import gallery, images
from app.creative.service import CreativeError, create_image, create_vector
from app.security.permissions import RiskLevel
from app.tools.base import Tool, ToolContext, ToolImage, ToolResult


def _shown(result, label: str) -> ToolResult:
    creation = result.creation
    note = (
        f"{label} generada y ya visible para el usuario (motor: {creation.engine}). "
        f"Guardada en: {gallery.path_of(creation)}. "
        "No describas la imagen en detalle ni repitas la ruta salvo que te la pidan: comenta en una frase y ofrece variaciones."
    )
    if creation.engine == "pollinations":
        note += (
            " Motor gratuito de calidad básica: no garantiza parecido con personas reales concretas, logos "
            "ni textos exactos. Si el pedido dependía de eso, díselo con honestidad (no afirmes que salió "
            "fiel) y menciona que con OpenAI la fidelidad al pedido es mucho mayor."
        )
    return ToolResult(success=True, data=note, images=[ToolImage(mime_type=creation.mime_type, data=base64.b64encode(result.data).decode("ascii"))])


class GenerateImageTool(Tool):
    name = "generate_image"
    description = (
        "Genera una imagen realista o artística (foto, retrato, paisaje, cuadro, arte conceptual, "
        "fondo de pantalla, producto...). Escribe `prompt` en INGLÉS, rico y concreto: sujeto, acción, "
        "entorno, estilo, iluminación, encuadre, colores. Para logos, íconos, diagramas o dibujos "
        "planos con texto usa draw_vector en su lugar. Ningún motor garantiza el parecido con una "
        "persona real concreta ni logos de marcas exactos: el resultado es una aproximación."
    )
    parameters = {
        "type": "object",
        "properties": {
            "prompt": {"type": "string", "description": "Descripción detallada en inglés."},
            "style": {"type": "string", "enum": sorted(images.STYLES), "description": "Estilo opcional que se suma al prompt."},
            "aspect": {"type": "string", "enum": sorted(images.ASPECTS), "description": "Formato. Por defecto cuadrado."},
            "engine": {"type": "string", "enum": ["auto", *images.ENGINES], "description": "auto salvo que el usuario pida un motor (openai = mejor calidad, de pago; pollinations = gratis)."},
        },
        "required": ["prompt"],
    }
    risk_level = RiskLevel.LOW_RISK

    def execute(self, params: dict, context: ToolContext) -> ToolResult:
        try:
            result = create_image(
                str(params.get("prompt", "")),
                engine=params.get("engine"),
                aspect=params.get("aspect"),
                style=params.get("style"),
            )
        except CreativeError as exc:
            return ToolResult(success=False, error=str(exc))
        return _shown(result, "Imagen")


class DrawVectorTool(Tool):
    name = "draw_vector"
    description = (
        "Dibuja una ilustración vectorial (SVG): logos, íconos, diagramas, infografías, pósters, "
        "personajes o escenas de estilo plano, tarjetas con texto. Describe en español qué dibujar, "
        "con estilo, colores y cualquier texto exacto que deba aparecer."
    )
    parameters = {
        "type": "object",
        "properties": {
            "description": {"type": "string", "description": "Qué dibujar, con estilo, paleta y textos."},
            "aspect": {"type": "string", "enum": sorted(images.ASPECTS), "description": "Formato. Por defecto cuadrado."},
        },
        "required": ["description"],
    }
    risk_level = RiskLevel.LOW_RISK

    def execute(self, params: dict, context: ToolContext) -> ToolResult:
        try:
            result = create_vector(str(params.get("description", "")), aspect=params.get("aspect"))
        except CreativeError as exc:
            return ToolResult(success=False, error=str(exc))
        return _shown(result, "Ilustración vectorial")
