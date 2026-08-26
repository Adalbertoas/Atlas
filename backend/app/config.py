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
    tts_provider: str = "mock"  # "sapi" | "mock"
    whisper_model_size: str = "base"

    smart_home_provider: str = "mock"  # "home_assistant" | "mock"
    smart_home_url: str = ""
    smart_home_token: str = ""

    vision_provider: str = "mock"  # "anthropic" | "mock"

    @property
    def is_production(self) -> bool:
        return self.app_env.lower() == "production"


@lru_cache
def get_settings() -> Settings:
    """Settings cacheado: se lee el entorno una sola vez por proceso."""
    return Settings()
