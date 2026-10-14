"""MockProvider: proveedor de IA determinista, sin red ni costo.

Sirve para desarrollar y correr los tests automatizados sin necesitar una
ANTHROPIC_API_KEY ni gastar créditos. Usa reglas simples por palabra clave
para decidir si debe llamar una tool o responder directo. No pretende ser
inteligente — solo ejercitar el flujo completo del Orchestrator.

Un mensaje con varios pedidos separados por "y además" o ";" produce una
tool por pedido, para poder probar los turnos con varias tools.
"""
from __future__ import annotations

import re

from app.ai.base import AIMessage, AIProvider, AIResponse, ToolCall, ToolSchema

_APP_ALIASES = ["vscode", "vs code", "notepad", "bloc de notas", "chrome", "explorer"]

# Palabras clave -> tema de query_world. Los militares van antes que "aviones".
_WORLD_TOPICS = [
    ("military_aircraft", ["aviones militares", "vuelos militares"]),
    ("aircraft", ["vuelos", "aviones"]),
    ("ships", ["barcos", "buques"]),
    ("earthquakes", ["terremoto", "sismo"]),
    ("satellite_image", ["imagen satelital", "imagen de satélite", "imagen de satelite"]),
    ("satellites", ["satélites", "satelites"]),
    ("fires", ["incendios"]),
    ("cyclones", ["ciclones", "huracanes"]),
    ("launches", ["lanzamientos"]),
    ("weather", ["clima", "tiempo hace"]),
]
_WORLD_PLACE = re.compile(r"\b(?:sobre|cerca de|en)\s+(.+)$", re.IGNORECASE)
_WORLD_SHOW = re.compile(
    r"\b(?:mostrame|mu[eé]strame|mostrar|ver|llevame a|ll[eé]vame a)\s+(.+?)\s+en el (?:mapa|globo|mundo)",
    re.IGNORECASE,
)
_FOLLOW_FLIGHT = re.compile(r"\bsegu[ií]\w*\s+(?:al?\s+|el\s+)?(?:vuelo|avi[oó]n)\s+(\S+)", re.IGNORECASE)
_FOLLOW_SATELLITE = re.compile(r"\bsegu[ií]\w*\s+(?:a\s+)?(?:la\s+|el\s+)?(?:sat[eé]lite\s+)?(.+)$", re.IGNORECASE)
_ROUTE = re.compile(r"\bruta de (.+?) a (.+)$", re.IGNORECASE)
_MAGNITUDE = re.compile(r"(?:mayor(?:es)?|m[aá]s|magnitud)\s+(?:a|de|que)?\s*(\d+(?:[.,]\d+)?)", re.IGNORECASE)
_REMINDER = re.compile(
    r"\brecord[aá]me\s+(.+?)\s+en\s+(\d+(?:[.,]\d+)?)\s+(segundo|minuto|hora)", re.IGNORECASE
)
_REMINDER_AT = re.compile(r"\brecord[aá]me\s+(.+?)\s+a las\s+(\d{1,2})(?::(\d{2}))?", re.IGNORECASE)
_WEB = re.compile(r"\bbusc[aá]\w*\s+(?:en|por)\s+(?:internet|la web)\s+(.+)$", re.IGNORECASE)
_DOCUMENTS = re.compile(r"\bbusc[aá]\w*\s+(.+?)\s+en mis documentos", re.IGNORECASE)
_SPLIT = re.compile(r"\s+y adem[aá]s\s+|\s*;\s*", re.IGNORECASE)
_SECONDS = {"segundo": 1 / 60, "minuto": 1, "hora": 60}


def _clean(text: str) -> str:
    return text.strip("¿?.!, ")


class MockProvider(AIProvider):
    def chat(
        self,
        messages: list[AIMessage],
        tools: list[ToolSchema] | None = None,
    ) -> AIResponse:
        available = {t.name for t in (tools or [])}

        # Si el último mensaje es un resultado de tool, ya no volvemos a
        # llamar una tool: generamos la respuesta final en texto.
        if messages and messages[-1].role == "tool":
            return AIResponse(text=self._final_answer(messages))

        last_user = next((m for m in reversed(messages) if m.role == "user"), None)
        content = last_user.content if last_user else ""

        calls = []
        for index, part in enumerate(_SPLIT.split(content), start=1):
            planned = self._plan(part, available)
            if planned:
                name, arguments = planned
                calls.append(ToolCall(id=f"mock-{index}", name=name, arguments=arguments))
        if calls:
            return AIResponse(tool_calls=calls)
        return AIResponse(text="Entendido. (respuesta simulada — configura AI_PROVIDER=anthropic para IA real)")

    def _plan(self, content: str, available: set[str]) -> tuple[str, dict] | None:
        """La tool (nombre, argumentos) que corresponde a un pedido, o None."""
        text = content.lower()

        def can(name: str) -> bool:
            return name in available

        if can("daily_briefing") and any(k in text for k in ["briefing", "resumen del día", "qué tengo hoy", "buen día"]):
            return "daily_briefing", {}

        if can("create_reminder") and (m := _REMINDER.search(content)):
            minutes = float(m.group(2).replace(",", ".")) * _SECONDS[m.group(3).lower()]
            return "create_reminder", {"message": _clean(m.group(1)), "in_minutes": minutes}
        if can("create_reminder") and (m := _REMINDER_AT.search(content)):
            at = f"{int(m.group(2)):02d}:{m.group(3) or '00'}"
            return "create_reminder", {"message": _clean(m.group(1)), "at": at}
        if can("list_reminders") and "recordatorios" in text:
            return "list_reminders", {}

        # Alertas antes que las consultas: "avisame si hay un terremoto" no es una pregunta.
        if can("create_world_alert") and any(k in text for k in ["avisame", "avísame", "alertame"]):
            place = _clean(m.group(1)) if (m := _WORLD_PLACE.search(content)) else ""
            if "iss" in text.split() or "estación espacial" in text:
                return "create_world_alert", {"topic": "satellite_pass", "place": place}
            topic = next((name for name, keys in _WORLD_TOPICS if any(k in text for k in keys)), "earthquakes")
            arguments = {"topic": topic, "place": place}
            if topic == "earthquakes" and (m := _MAGNITUDE.search(content)):
                arguments["min_magnitude"] = float(m.group(1).replace(",", "."))
                # "mayor a 5 cerca de Chile": el lugar es lo que sigue al número.
                arguments["place"] = _clean(m2.group(1)) if (m2 := _WORLD_PLACE.search(content[m.end():])) else ""
            return "create_world_alert", arguments
        if can("list_world_alerts") and "alertas" in text:
            return "list_world_alerts", {}

        if can("show_world_view"):
            if m := _ROUTE.search(content):
                places = [_clean(m.group(1)), _clean(m.group(2))]
                return "show_world_view", {"marks": [{"type": "route", "places": places, "label": "Ruta"}]}
            if m := _FOLLOW_FLIGHT.search(content):
                return "show_world_view", {"follow_aircraft": _clean(m.group(1))}
            if re.search(r"\bsegu[ií]", text) and (m := _FOLLOW_SATELLITE.search(content)):
                return "show_world_view", {"follow_satellite": _clean(m.group(1))}
            # Antes que la regla de la hora: "ahora" contiene "hora".
            if m := _WORLD_SHOW.search(content):
                return "show_world_view", {"place": m.group(1).strip()}

        if can("web_search") and (m := _WEB.search(content)):
            return "web_search", {"query": _clean(m.group(1))}
        if can("search_documents") and (m := _DOCUMENTS.search(content)):
            return "search_documents", {"query": _clean(m.group(1))}

        if can("read_clipboard") and any(k in text for k in ["portapapeles", "lo que copié", "lo que copie"]):
            return "read_clipboard", {}
        if can("save_screenshot") and "captura" in text and any(k in text for k in ["guard", "sac", "tom"]):
            return "save_screenshot", {}
        if can("manage_window") and "ventana" in text:
            actions = {"izquierda": "left", "derecha": "right", "maximiz": "maximize", "minimiz": "minimize"}
            action = next((value for key, value in actions.items() if key in text), None)
            if action:
                return "manage_window", {"action": action}

        if can("query_world"):
            topic = next((name for name, keys in _WORLD_TOPICS if any(k in text for k in keys)), None)
            if topic:
                arguments = {"topic": topic}
                if m := _WORLD_PLACE.search(content):
                    arguments["place"] = _clean(m.group(1))
                return "query_world", arguments

        if can("get_current_time") and any(k in text for k in ["hora", "fecha"]):
            return "get_current_time", {}

        if can("get_system_info") and any(
            k in text for k in ["ram", "cpu", "memoria ram", "disco", "estado del sistema", "sistema"]
        ):
            return "get_system_info", {}

        if can("open_application") and any(k in text for k in ["abre", "abrir", "abreme"]):
            app = next((a for a in _APP_ALIASES if a in text), "notepad")
            return "open_application", {"application_name": app}

        if can("search_memory") and ("recuerdas" in text or "recuerda" in text and "qué" in text):
            m = re.search(r"sobre (.+)", text)
            return "search_memory", {"query": m.group(1).strip("? ") if m else ""}

        if can("create_memory") and any(k in text for k in ["anota", "recuerda que", "guarda que"]):
            return "create_memory", {"content": content, "category": "personal"}

        if can("search_files") and "busca" in text and "archivo" in text:
            m = re.search(r"archivos? (?:que contengan |llamados? )?(.+)", text)
            return "search_files", {"query": m.group(1).strip() if m else ""}

        if can("list_files") and "lista" in text and "archivo" in text:
            return "list_files", {"path": "."}

        return None

    def _final_answer(self, messages: list[AIMessage]) -> str:
        # Todos los resultados de tool que siguen al último pedido del modelo.
        results = []
        for message in reversed(messages):
            if message.role != "tool":
                break
            results.append(f"Resultado de {message.name}: {message.content}")
        return "Listo. " + "\n".join(reversed(results))
