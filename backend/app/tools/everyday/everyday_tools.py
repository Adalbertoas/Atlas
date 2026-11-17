"""Tools del día a día: clima, noticias, divisas, calculadora, contraseñas,
abrir sitios web, volumen exacto y bloquear la PC."""
from __future__ import annotations

import ctypes
import re
import secrets
import string
import webbrowser
from urllib.parse import urlparse

from app.config import get_settings
from app.everyday import calculator, currency, news, weather
from app.personality.service import get_profile
from app.security.permissions import RiskLevel
from app.tools.base import Tool, ToolContext, ToolResult
from app.web.client import WebError


def default_city(context: ToolContext) -> str:
    """La ciudad del perfil (Configuración → Personalidad) o HOME_PLACE del .env."""
    try:
        city = get_profile(context.db).home_city.strip()
    except Exception:  # noqa: BLE001 - sin perfil: se usa la config
        city = ""
    return city or get_settings().home_place.strip()


class GetWeatherTool(Tool):
    name = "get_weather"
    description = (
        "Clima actual y pronóstico de los próximos días para una ciudad. Si el usuario no dice "
        "dónde, omite 'place' y se usa su ciudad configurada."
    )
    parameters = {
        "type": "object",
        "properties": {
            "place": {"type": "string", "description": "Ciudad, opcionalmente con país: 'Madrid, España'."},
            "days": {"type": "integer", "description": "Días de pronóstico (1-7). Por defecto 3."},
        },
        "required": [],
    }
    risk_level = RiskLevel.READ_ONLY

    def execute(self, params: dict, context: ToolContext) -> ToolResult:
        place = str(params.get("place") or "").strip() or default_city(context)
        if not place:
            return ToolResult(
                success=False,
                error="No sé de qué ciudad. Pregúntale al usuario, o que la configure en Configuración → Personalidad.",
            )
        try:
            return ToolResult(success=True, data=weather.get_weather(place, int(params.get("days") or 3)).summary())
        except WebError as exc:
            return ToolResult(success=False, error=str(exc))


class GetNewsTool(Tool):
    name = "get_news"
    description = (
        "Titulares de noticias recientes en español. Sin 'query' devuelve los principales; con un "
        "tema (tecnología, deportes, economía, ciencia, salud, mundo) o cualquier búsqueda, los de ese tema."
    )
    parameters = {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "Tema o búsqueda. Vacío = principales titulares."},
            "limit": {"type": "integer", "description": "Cantidad de titulares (1-20). Por defecto 8."},
        },
        "required": [],
    }
    risk_level = RiskLevel.READ_ONLY

    def execute(self, params: dict, context: ToolContext) -> ToolResult:
        try:
            headlines = news.get_news(str(params.get("query") or ""), int(params.get("limit") or 8))
        except WebError as exc:
            return ToolResult(success=False, error=str(exc))
        if not headlines:
            return ToolResult(success=True, data="No encontré noticias sobre eso.")
        lines = [f"- {h.title} ({h.source}{', ' + h.published if h.published else ''})" for h in headlines]
        return ToolResult(success=True, data="\n".join(lines))


class ConvertCurrencyTool(Tool):
    name = "convert_currency"
    description = "Convierte un monto entre monedas con la cotización del día (USD, EUR, DOP, MXN, etc.)."
    parameters = {
        "type": "object",
        "properties": {
            "amount": {"type": "number", "description": "Monto a convertir."},
            "from_currency": {"type": "string", "description": "Código ISO de origen, ej. USD."},
            "to_currency": {"type": "string", "description": "Código ISO de destino, ej. DOP."},
        },
        "required": ["amount", "from_currency", "to_currency"],
    }
    risk_level = RiskLevel.READ_ONLY

    def execute(self, params: dict, context: ToolContext) -> ToolResult:
        try:
            amount = float(params.get("amount"))
            result = currency.convert(amount, str(params.get("from_currency", "")), str(params.get("to_currency", "")))
        except (TypeError, ValueError):
            return ToolResult(success=False, error="El monto no es un número válido.")
        except WebError as exc:
            return ToolResult(success=False, error=str(exc))
        return ToolResult(
            success=True,
            data=(
                f"{calculator.format_number(result['amount'])} {result['from']} = "
                f"{calculator.format_number(round(result['result'], 2))} {result['to']} "
                f"(1 {result['from']} = {result['rate']:.4f} {result['to']}; actualizado {result['updated']})."
            ),
        )


class CalculateTool(Tool):
    name = "calculate"
    description = (
        "Calcula expresiones matemáticas con precisión: + - * / ** %, paréntesis, sqrt, sin, cos, "
        "log, factorial, pi, etc. Úsala en vez de calcular de memoria. '15% de 200' también funciona."
    )
    parameters = {
        "type": "object",
        "properties": {"expression": {"type": "string", "description": "Ej.: (1500*1.18)/12"}},
        "required": ["expression"],
    }
    risk_level = RiskLevel.READ_ONLY

    def execute(self, params: dict, context: ToolContext) -> ToolResult:
        expression = str(params.get("expression", ""))
        try:
            value = calculator.calculate(expression)
        except calculator.CalculatorError as exc:
            return ToolResult(success=False, error=str(exc))
        return ToolResult(success=True, data=f"{expression.strip()} = {calculator.format_number(value)}")


class GeneratePasswordTool(Tool):
    name = "generate_password"
    description = "Genera una contraseña aleatoria segura. Muéstrasela al usuario; no la guardes en memoria."
    parameters = {
        "type": "object",
        "properties": {
            "length": {"type": "integer", "description": "Largo (8-128). Por defecto 20."},
            "symbols": {"type": "boolean", "description": "Incluir símbolos. Por defecto sí."},
        },
        "required": [],
    }
    risk_level = RiskLevel.READ_ONLY

    def execute(self, params: dict, context: ToolContext) -> ToolResult:
        try:
            length = max(8, min(int(params.get("length") or 20), 128))
        except (TypeError, ValueError):
            length = 20
        use_symbols = params.get("symbols", True) is not False
        groups = [string.ascii_lowercase, string.ascii_uppercase, string.digits]
        if use_symbols:
            groups.append("!@#$%&*-_=+?")
        alphabet = "".join(groups)
        # Al menos un carácter de cada grupo, en posición aleatoria.
        chars = [secrets.choice(g) for g in groups] + [secrets.choice(alphabet) for _ in range(length - len(groups))]
        secrets.SystemRandom().shuffle(chars)
        return ToolResult(success=True, data="".join(chars))


class OpenWebsiteTool(Tool):
    name = "open_website"
    description = "Abre una página web en el navegador predeterminado (ej. youtube.com, una URL completa)."
    parameters = {
        "type": "object",
        "properties": {"url": {"type": "string", "description": "Dirección: 'youtube.com' o 'https://...'"}},
        "required": ["url"],
    }
    risk_level = RiskLevel.LOW_RISK

    def execute(self, params: dict, context: ToolContext) -> ToolResult:
        url = str(params.get("url", "")).strip()
        if not url:
            return ToolResult(success=False, error="Falta la dirección.")
        # "javascript:...", "file:..." y similares: otro esquema, no una dirección sin "https://".
        # "localhost:3000" sí pasa (después de los dos puntos viene un puerto).
        if "://" not in url and re.match(r"^[a-zA-Z][\w+.-]*:(?!\d)", url):
            return ToolResult(success=False, error="Solo abro direcciones web (http o https).")
        if "://" not in url:
            url = "https://" + url
        parsed = urlparse(url)
        try:
            valid = parsed.scheme in ("http", "https") and bool(parsed.hostname) and " " not in parsed.netloc
            parsed.port  # noqa: B018 - lanza ValueError si el puerto no es un número
        except ValueError:
            valid = False
        if not valid:
            return ToolResult(success=False, error="Solo abro direcciones web (http o https).")
        try:
            webbrowser.open(url)
        except Exception as exc:  # noqa: BLE001
            return ToolResult(success=False, error=str(exc))
        return ToolResult(success=True, data=f"Abrí {url} en el navegador.")


VK_VOLUME_DOWN = 0xAE
VK_VOLUME_UP = 0xAF


def _press(vk: int, times: int) -> None:
    for _ in range(times):
        ctypes.windll.user32.keybd_event(vk, 0, 0x1, 0)
        ctypes.windll.user32.keybd_event(vk, 0, 0x1 | 0x2, 0)


class SetVolumeTool(Tool):
    name = "set_volume"
    description = "Pone el volumen general de Windows en un porcentaje exacto (0-100)."
    parameters = {
        "type": "object",
        "properties": {"level": {"type": "integer", "description": "Porcentaje 0-100."}},
        "required": ["level"],
    }
    risk_level = RiskLevel.LOW_RISK

    def execute(self, params: dict, context: ToolContext) -> ToolResult:
        try:
            level = max(0, min(int(params.get("level")), 100))
        except (TypeError, ValueError):
            return ToolResult(success=False, error="El nivel debe ser un número entre 0 y 100.")
        try:
            # Cada tecla de volumen mueve 2 %: se baja a 0 y se sube hasta el nivel pedido.
            _press(VK_VOLUME_DOWN, 50)
            _press(VK_VOLUME_UP, round(level / 2))
        except Exception as exc:  # noqa: BLE001
            return ToolResult(success=False, error=str(exc))
        return ToolResult(success=True, data=f"Volumen al {level} %.")


class LockComputerTool(Tool):
    name = "lock_computer"
    description = "Bloquea la sesión de Windows (como Win+L). No cierra nada."
    parameters = {"type": "object", "properties": {}, "required": []}
    risk_level = RiskLevel.LOW_RISK

    def execute(self, params: dict, context: ToolContext) -> ToolResult:
        try:
            if not ctypes.windll.user32.LockWorkStation():
                return ToolResult(success=False, error="Windows no permitió bloquear la sesión.")
        except Exception as exc:  # noqa: BLE001
            return ToolResult(success=False, error=str(exc))
        return ToolResult(success=True, data="Sesión bloqueada.")
