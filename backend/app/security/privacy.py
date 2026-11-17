"""Informe de privacidad: qué datos salen de esta PC y a dónde, según la configuración activa.

Se arma solo a partir de Settings, sin consultar nada externo. Cada flujo
tiene un destino: "local" (no sale de la PC), "network" (va a otro equipo de
tu red), "external" (sale a internet) u "off" (función apagada o simulada).
"""
from __future__ import annotations

import ipaddress
from urllib.parse import urlparse

from app.config import Settings


def _where(url: str) -> str:
    """Clasifica una URL: local (esta PC), network (red privada) o external."""
    host = (urlparse(url).hostname or "").lower()
    if host in ("localhost", ""):
        return "local"
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        # Un nombre: los de red local suelen terminar así; el resto se asume internet.
        return "network" if host.endswith((".local", ".lan", ".home")) else "external"
    if ip.is_loopback:
        return "local"
    return "network" if ip.is_private else "external"


def _flow(area: str, provider: str, destination: str, sends: str) -> dict:
    return {"area": area, "provider": provider, "destination": destination, "sends": sends}


def build_privacy_report(settings: Settings) -> list[dict]:
    flows: list[dict] = []

    if settings.ai_provider == "anthropic":
        flows.append(
            _flow(
                "Inteligencia (chat)",
                f"Anthropic — {settings.anthropic_model}",
                "external",
                "Tus mensajes, el historial de la conversación y el resultado de cada herramienta que "
                "ATLAS usa: memorias consultadas, texto del portapapeles, fragmentos de documentos, "
                "páginas web leídas y datos del mundo.",
            )
        )
    elif settings.ai_provider == "ollama":
        destination = _where(settings.ollama_base_url)
        flows.append(
            _flow(
                "Inteligencia (chat)",
                f"Ollama — {settings.ollama_model}",
                destination,
                "Tus mensajes y los resultados de las herramientas se procesan en "
                + ("esta PC." if destination == "local" else f"el servidor Ollama de {settings.ollama_base_url}."),
            )
        )
    else:
        flows.append(
            _flow("Inteligencia (chat)", "Simulada (mock)", "off", "Respuestas por palabras clave; no se envía nada.")
        )

    flows.append(
        _flow("Voz a texto", f"Whisper local ({settings.whisper_model_size})", "local", "El audio se transcribe en esta PC.")
        if settings.stt_provider == "whisper"
        else _flow("Voz a texto", "Simulada (mock)", "off", "No se procesa audio.")
    )

    if settings.tts_provider in ("kokoro", "sapi"):
        name = "Kokoro" if settings.tts_provider == "kokoro" else "Voces de Windows (SAPI)"
        flows.append(_flow("Texto a voz", name, "local", "La voz se genera en esta PC."))
    else:
        flows.append(_flow("Texto a voz", "Simulada (mock)", "off", "No se genera voz."))

    flows.append(
        _flow(
            "Visión",
            "Anthropic",
            "external",
            "Las capturas de pantalla e imágenes que le pedís analizar. Cada captura pide confirmación antes.",
        )
        if settings.vision_provider == "anthropic"
        else _flow("Visión", "Simulada (mock)", "off", "No se envían imágenes.")
    )

    if settings.smart_home_provider == "home_assistant":
        flows.append(
            _flow(
                "Hogar",
                f"Home Assistant — {settings.smart_home_url}",
                _where(settings.smart_home_url),
                "Órdenes y consultas de estado de tus dispositivos.",
            )
        )
    else:
        flows.append(_flow("Hogar", "Simulado (mock)", "off", "Dispositivos de prueba; no se controla nada real."))

    if settings.gods_eye_url.strip():
        flows.append(
            _flow(
                "Mundo",
                "Gods Eye View (en esta PC) y sus fuentes públicas",
                "external",
                "Los nombres de lugares y zonas que consultás, a un geocodificador público y a las fuentes "
                "de cada capa (vuelos, sismos, clima, satélites). Las alertas repiten esas consultas solas.",
            )
        )
    else:
        flows.append(_flow("Mundo", "Desactivado", "off", "Sin consultas geoespaciales."))

    if settings.web_enabled:
        engine = "Brave Search" if settings.brave_api_key else "DuckDuckGo / Wikipedia"
        flows.append(
            _flow(
                "Internet",
                engine,
                "external",
                "Lo que ATLAS busca, al buscador; y tu dirección IP a cada página que lee.",
            )
        )
        flows.append(
            _flow(
                "Clima, noticias y divisas",
                "Open-Meteo, Google News y open.er-api.com",
                "external",
                "El nombre de la ciudad del clima, el tema de las noticias y las monedas que convertís.",
            )
        )
    else:
        flows.append(_flow("Internet", "Desactivado", "off", "ATLAS no busca ni lee páginas web."))

    flows.append(
        _flow(
            "Datos guardados",
            settings.database_url.split("///")[-1] if settings.database_url.startswith("sqlite") else "Base de datos",
            "local" if settings.database_url.startswith("sqlite") else _where(settings.database_url),
            "Conversaciones, memoria, recordatorios, alertas, notificaciones y el registro de actividad.",
        )
    )

    flows.append(
        _flow(
            "Acceso a ATLAS",
            "Con contraseña" if settings.auth_enabled else "Sin contraseña",
            "network",
            "El servidor acepta conexiones de tu red (para el celular). "
            + (
                "Solo entra quien tenga la contraseña."
                if settings.auth_enabled
                else "Cualquiera conectado a tu red puede usar ATLAS y controlar esta PC."
            ),
        )
    )
    return flows
