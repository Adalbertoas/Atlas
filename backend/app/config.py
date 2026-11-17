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

    ai_provider: str = "mock"  # "ollama" | "anthropic" | "mock"
    ollama_base_url: str = "http://127.0.0.1:11434"
    ollama_model: str = "qwen3:4b"
    anthropic_api_key: str = ""
    anthropic_model: str = "claude-sonnet-4-5-20250929"

    jwt_secret: str = "changeme-generate-a-real-secret"
    jwt_expire_minutes: int = 1440
    # Sistema de un solo usuario (no multi-tenant): una contraseña, no una
    # tabla de usuarios. Se compara contra esta variable de entorno, igual
    # criterio que las demás credenciales del proyecto.
    atlas_password: str = ""
    # false = sin login: toda la API queda abierta a cualquiera que alcance
    # el puerto 8000 (incluida la WiFi, el backend escucha en 0.0.0.0).
    auth_enabled: bool = True

    stt_provider: str = "mock"  # "whisper" | "mock"
    tts_provider: str = "mock"  # "kokoro" | "sapi" | "mock"
    whisper_model_size: str = "base"
    kokoro_voice: str = "ef_dora"  # voz española local de Kokoro
    kokoro_speed: float = 1.0
    kokoro_cache_dir: str = ""
    # Verificación de hablante ("solo responder a mi voz"). Vacío = rutas por
    # defecto: el modelo en .cache/speaker/ y la huella en backend/speaker_profile.json.
    speaker_model_path: str = ""
    speaker_profile_path: str = ""

    smart_home_provider: str = "mock"  # "home_assistant" | "mock"
    smart_home_url: str = ""
    smart_home_token: str = ""

    vision_provider: str = "mock"  # "anthropic" | "mock"

    # Consola geoespacial local (integrations/gods-eye-view). Vacío = sin
    # herramientas de mundo. Debe ser loopback: su /mcp rechaza otros hosts.
    gods_eye_url: str = "http://127.0.0.1:4173"

    # Briefing diario: lugar para el clima y hora ("HH:MM") a la que se
    # notifica solo. Vacíos = sin clima / solo cuando se lo pidas.
    home_place: str = ""
    briefing_time: str = ""

    # Acceso a internet (web_search / read_web_page). Con BRAVE_API_KEY usa
    # la API de Brave Search; sin ella, DuckDuckGo y Wikipedia.
    web_enabled: bool = True
    brave_api_key: str = ""

    # Creatividad: imágenes y dibujos vectoriales.
    # Motores de imagen: "openai" (gpt-image, de pago, necesita OPENAI_API_KEY),
    # "pollinations" (gratis, sin clave; el prompt se envía a pollinations.ai).
    # "auto" usa OpenAI si hay clave y si no Pollinations.
    image_default_engine: str = "auto"
    openai_api_key: str = ""
    openai_image_model: str = "gpt-image-1"
    openai_image_quality: str = "medium"  # "low" | "medium" | "high"
    # Modelo de Claude que dibuja los SVG (necesita AI_PROVIDER=anthropic).
    creative_model: str = "claude-opus-5-5"
    # Carpeta donde se guardan las creaciones. Vacío = Imágenes\ATLAS del usuario.
    creative_dir: str = ""

    @property
    def is_production(self) -> bool:
        return self.app_env.lower() == "production"


@lru_cache
def get_settings() -> Settings:
    """Settings cacheado: se lee el entorno una sola vez por proceso."""
    return Settings()
