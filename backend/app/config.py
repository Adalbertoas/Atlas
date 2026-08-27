"""Configuración central de ATLAS.

Todos los valores se leen de variables de entorno (ver .env.example).
Nunca se deben hardcodear credenciales aquí ni en ningún otro módulo.
"""
from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_env: str = "development"
    log_level: str = "INFO"

    database_url: str = "sqlite:///./atlas.db"
    redis_url: str = "redis://localhost:6379/0"

    ai_provider: str = "mock"  # "anthropic" | "mock"
    anthropic_api_key: str = ""
    anthropic_model: str = "claude-sonnet-4-5-20250929"

    jwt_secret: str = "changeme-generate-a-real-secret"
    jwt_expire_minutes: int = 1440
    # Sistema de un solo usuario (no multi-tenant): una contraseña, no una
    # tabla de usuarios. Se compara contra esta variable de entorno, igual
    # criterio que las demás credenciales del proyecto.
    atlas_password: str = ""

    stt_provider: str = "mock"  # "whisper" | "mock"
    tts_provider: str = "mock"  # "edge" | "sapi" | "mock"
    whisper_model_size: str = "base"

    # Voz neuronal de Edge (solo si tts_provider="edge"). rate/pitch aceptan
    # el formato de la propia API: "+10%", "-5%", "+0Hz".
    edge_tts_voice: str = "es-MX-JorgeNeural"
    edge_tts_rate: str = "+0%"
    edge_tts_pitch: str = "+0Hz"

    smart_home_provider: str = "mock"  # "home_assistant" | "tuya" | "mock"
    smart_home_url: str = ""
    smart_home_token: str = ""

    # Tuya Cloud (Fase 12): cubre las apps de marca blanca sobre Tuya, como
    # Mercury Smart. El endpoint depende del centro de datos del proyecto.
    tuya_access_id: str = ""
    tuya_access_secret: str = ""
    tuya_endpoint: str = "https://openapi.tuyaus.com"
    tuya_uid: str = ""

    vision_provider: str = "mock"  # "anthropic" | "mock"

    # --- Integraciones externas (Fase 10) ---
    # Wikipedia y el clima (Open-Meteo) no necesitan key, funcionan siempre.
    # YouTube y Spotify sí: si falta la key/credencial, la tool respectiva
    # devuelve un error explicando qué falta en vez de romper el resto de
    # ATLAS (mismo criterio que smart_home_provider/vision_provider).
    youtube_api_key: str = ""
    spotify_client_id: str = ""
    spotify_client_secret: str = ""
    # Reconocimiento de canciones (tipo Shazam) vía AudD — no una tool de la
    # IA como las de arriba, sino un endpoint de subida directa (mismo
    # criterio que /voice/transcribe y /vision/analyze: el usuario ya
    # decidió explícitamente grabar/mandar el audio).
    audd_api_token: str = ""

    # Búsqueda web (Fase 19). "duckduckgo" no necesita nada; "tavily" da
    # mejores resultados y una respuesta ya sintetizada, pero pide cuenta.
    web_search_provider: str = "duckduckgo"  # "duckduckgo" | "tavily"
    tavily_api_key: str = ""

    # Nombre para el saludo del dashboard ("¡Hola, X!"). Vacío por defecto:
    # sin nombre configurado el saludo es genérico ("¡Hola!"), en vez de
    # inventar uno. Sistema de un solo usuario, no hay tabla de usuarios.
    atlas_user_name: str = ""

    # Palabra de activación por voz. Vive acá y no en cada cliente para que
    # el escritorio, el dashboard y la PWA no se desincronicen: cambiarla en
    # un solo lugar la cambia en los tres. Se eligió "Ali" tras probar en
    # vivo que Whisper (forzado a español) no reconocía "Vision".
    atlas_wake_word: str = "ali"

    @property
    def is_production(self) -> bool:
        return self.app_env.lower() == "production"


@lru_cache
def get_settings() -> Settings:
    """Settings cacheado: se lee el entorno una sola vez por proceso."""
    return Settings()
