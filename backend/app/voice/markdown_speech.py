"""Convierte Markdown a texto plano hablable, antes de mandarlo al TTS.

Claude responde en Markdown, y los motores de voz leen la marcación tal
cual: "asterisco asterisco importante asterisco asterisco". Peor aún con
los enlaces, donde dictaba la URL entera carácter por carácter.

Vive en el backend y no en cada cliente a propósito: el escritorio, el
dashboard y la PWA usan todos /api/v1/voice/speak, así que arreglarlo acá
lo arregla en los tres.

Solo afecta a lo que se **habla**. El texto que se muestra en pantalla
sigue llegando en Markdown, para que cada cliente lo renderice como texto
enriquecido.
"""
from __future__ import annotations

import re

# Bloques de código: se anuncian en vez de dictarse. Leer código línea por
# línea (llaves, paréntesis, guiones bajos) es inservible en voz.
_CODE_BLOCK = re.compile(r"```[\w+-]*\n(.*?)```", re.DOTALL)
_INLINE_CODE = re.compile(r"`([^`\n]+)`")

# Enlaces e imágenes: se queda el texto, se descarta la URL.
_IMAGE = re.compile(r"!\[([^\]]*)\]\([^)]*\)")
_LINK = re.compile(r"\[([^\]]+)\]\([^)]*\)")
_BARE_URL = re.compile(r"https?://\S+")

# Énfasis. El orden importa: primero los dobles, si no `**x**` deja `*x*`.
_BOLD_ITALIC = re.compile(r"(\*\*\*|___)(.+?)\1", re.DOTALL)
_BOLD = re.compile(r"(\*\*|__)(.+?)\1", re.DOTALL)
_ITALIC = re.compile(r"(?<![\w*])[*_]([^*_\n]+)[*_](?![\w*])")
_STRIKE = re.compile(r"~~(.+?)~~", re.DOTALL)

_HEADING = re.compile(r"^\s{0,3}#{1,6}\s*", re.MULTILINE)
_BLOCKQUOTE = re.compile(r"^\s{0,3}>\s?", re.MULTILINE)
_HRULE = re.compile(r"^\s{0,3}([-*_])\s*(?:\1\s*){2,}$", re.MULTILINE)
_BULLET = re.compile(r"^\s*[-*+]\s+", re.MULTILINE)
_TABLE_SEPARATOR = re.compile(r"^\s*\|?[\s:|-]+\|[\s:|-]*$", re.MULTILINE)

_MULTIPLE_BLANK_LINES = re.compile(r"\n{3,}")
_MULTIPLE_SPACES = re.compile(r"[ \t]{2,}")

# Emoji y pictogramas: los motores de voz o los ignoran o los nombran
# ("cara sonriente"), que interrumpe la frase.
_PICTOGRAPHS = re.compile(
    "[\U0001f000-\U0001faff☀-➿⬀-⯿⌀-⏿️]"
)


def markdown_to_speech(text: str) -> str:
    """Devuelve el texto listo para dictar. Nunca lanza: ante cualquier
    entrada rara devuelve algo pronunciable, porque quedarse sin voz es peor
    que leer un asterisco suelto."""
    if not text:
        return ""

    result = _CODE_BLOCK.sub(lambda m: " (bloque de código) ", text)
    result = _INLINE_CODE.sub(r"\1", result)

    result = _IMAGE.sub(r"\1", result)
    result = _LINK.sub(r"\1", result)
    result = _BARE_URL.sub(" (enlace) ", result)

    result = _BOLD_ITALIC.sub(r"\2", result)
    result = _BOLD.sub(r"\2", result)
    result = _STRIKE.sub(r"\1", result)
    result = _ITALIC.sub(r"\1", result)

    result = _HRULE.sub("", result)
    result = _HEADING.sub("", result)
    result = _BLOCKQUOTE.sub("", result)
    result = _TABLE_SEPARATOR.sub("", result)
    # Las viñetas se vuelven pausa: sin esto, una lista se lee como una sola
    # frase interminable.
    result = _BULLET.sub("", result)
    result = result.replace("|", " ")

    result = _PICTOGRAPHS.sub("", result)
    result = _MULTIPLE_SPACES.sub(" ", result)
    result = _MULTIPLE_BLANK_LINES.sub("\n\n", result)

    # Cada línea que quedó suelta pasa a terminar en punto, para que el motor
    # haga la pausa que corresponde entre ítems de una lista.
    lines = []
    for line in result.split("\n"):
        stripped = line.strip()
        if not stripped:
            continue
        if stripped[-1] not in ".!?:;,":
            stripped += "."
        lines.append(stripped)

    return " ".join(lines).strip()
