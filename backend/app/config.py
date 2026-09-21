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
    # Límite de gasto estimado en la API de Anthropic (Fase 28). 0 = sin
    # tope. No es la factura real, es una estimación por tabla de precios
    # (ver app/core/usage.py) — un guardarraíl barato, no un medidor exacto.
    anthropic_daily_budget_usd: float = 5.0
    anthropic_monthly_budget_usd: float = 0.0

    # Agent Platform (Fase 10). Estos topes son deliberadamente pequeños:
    # una tarea personal normal no necesita decenas de acciones autónomas.
    agent_max_steps: int = 12
    agent_max_tool_calls: int = 20
    agent_timeout_seconds: int = 120

    jwt_secret: str = "changeme-generate-a-real-secret"
    jwt_expire_minutes: int = 1440
    # Rate limiting de /auth/login (sección 5, endurecido): tras
    # login_max_attempts fallos seguidos desde la misma IP, se bloquea por
    # login_lockout_seconds. Sistema de un solo usuario: nadie legítimo
    # necesita más de 5 intentos para acordarse de su propia contraseña.
    login_max_attempts: int = 5
    login_lockout_seconds: int = 900

    # Backups automáticos de la base de datos (Fase 26). Solo aplica a
    # SQLite (ver app/core/backup.py). Uno al arrancar + uno cada
    # backup_interval_hours mientras el proceso sigue corriendo; se
    # conservan los backup_keep_count más recientes.
    backup_enabled: bool = True
    backup_dir: str = "backups"
    backup_interval_hours: int = 24
    backup_keep_count: int = 7
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

    # Búsqueda semántica de memoria (fastembed local, gratis, sin API key).
    # "mock" por defecto: no descarga ningún modelo, para no obligar a
    # tenerlo instalado solo para correr tests o levantar el server rápido.
    embedding_provider: str = "mock"  # "fastembed" | "mock"
    embedding_model: str = "sentence-transformers/all-MiniLM-L6-v2"

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

    # --- Google Calendar (Fase 21) ---
    # OAuth2 "instalada" (loopback): no hay servidor propio que reciba el
    # redirect, `scripts/google_calendar_setup.py` levanta uno temporal en
    # localhost solo durante el consentimiento. Mismo criterio que
    # YouTube/Spotify/AudD: sin credenciales, la tool devuelve un error
    # explicando qué falta en vez de romper el resto de ATLAS.
    google_client_id: str = ""
    google_client_secret: str = ""
    # Se obtiene una sola vez corriendo el script de setup y no expira
    # (a diferencia del access_token, que dura ~1h y se refresca solo).
    google_refresh_token: str = ""
    # "primary" = el calendario principal de la cuenta. Se puede apuntar a
    # otro calendario por su ID (visible en la configuración de Google
    # Calendar, sección "Integrar calendario").
    google_calendar_id: str = "primary"

    # --- Push notifications reales (Fase 22, Web Push/VAPID) ---
    # Generadas una sola vez con scripts/generate_vapid_keys.py — el par
    # identifica a ATLAS ante los servicios push de los navegadores
    # (Chrome/Firefox/Edge), no depende de ninguna cuenta externa.
    vapid_public_key: str = ""
    vapid_private_key: str = ""
    # "mailto:" + un email de contacto real: es el claim `sub` que exige el
    # protocolo VAPID — permite que el servicio push del navegador contacte
    # al dueño de la app si algo sale mal (ej. exceso de envíos).
    vapid_contact_email: str = ""

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
