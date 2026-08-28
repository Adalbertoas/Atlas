"""Rate limiting de /auth/login (sección 5, endurecido).

ATLAS es de un solo usuario, pero desde que existen clientes remotos
(móvil, dashboard por red local) cualquiera con acceso a la WiFi puede
probar `ATLAS_PASSWORD` sin límite — no había nada que lo impidiera. Esto
cierra ese hueco con un bloqueo simple por IP: no es 2FA ni reemplaza una
contraseña fuerte, pero convierte un ataque de fuerza bruta práctico en uno
que tardaría años.

Estado en memoria de proceso, mismo criterio que PermissionManager: para un
solo usuario en un solo proceso alcanza. Si el sistema escala a múltiples
workers, este store también debería moverse a algo compartido (Redis).
"""
from __future__ import annotations

import time
from dataclasses import dataclass

from app.config import get_settings


@dataclass
class _Attempts:
    failures: int = 0
    locked_until: float = 0.0


class LoginRateLimiter:
    def __init__(self, max_attempts: int | None = None, lockout_seconds: int | None = None) -> None:
        settings = get_settings()
        self._max_attempts = max_attempts if max_attempts is not None else settings.login_max_attempts
        self._lockout_seconds = (
            lockout_seconds if lockout_seconds is not None else settings.login_lockout_seconds
        )
        self._by_ip: dict[str, _Attempts] = {}

    def seconds_until_unlocked(self, ip: str) -> float:
        """0 si no está bloqueada. > 0 = cuántos segundos faltan."""
        attempts = self._by_ip.get(ip)
        if attempts is None:
            return 0.0
        remaining = attempts.locked_until - time.monotonic()
        return max(0.0, remaining)

    def record_failure(self, ip: str) -> None:
        attempts = self._by_ip.setdefault(ip, _Attempts())
        attempts.failures += 1
        if attempts.failures >= self._max_attempts:
            attempts.locked_until = time.monotonic() + self._lockout_seconds

    def record_success(self, ip: str) -> None:
        """Un login correcto limpia el historial — no tiene sentido seguir
        contando intentos fallidos viejos contra el dueño real de la cuenta."""
        self._by_ip.pop(ip, None)


# Instancia única a nivel de proceso, mismo patrón que permission_manager.
login_rate_limiter = LoginRateLimiter()


class RequestRateLimiter:
    """Límite genérico de requests por IP en una ventana deslizante.

    A diferencia de LoginRateLimiter (bloqueo largo tras fallos), esto
    protege endpoints ya autenticados (ej. /chat) de un cliente que manda
    ráfagas — por un token filtrado, un bug de reintento en el cliente, o
    un loop de automatización mal configurado. El budget de la Fase 28
    (`app/core/usage.py`) frena el gasto en tokens de Claude, pero no evita
    que el proceso mismo se sature respondiendo de más en poco tiempo.

    Ventana fija, no deslizante de verdad: alcanza para el propósito (un
    freno barato) y es más simple que llevar timestamps por request.
    """

    def __init__(self, max_requests: int, window_seconds: float) -> None:
        self._max_requests = max_requests
        self._window_seconds = window_seconds
        self._by_ip: dict[str, tuple[int, float]] = {}  # ip -> (count, window_start)

    def check(self, ip: str) -> float:
        """0.0 si el request puede pasar. > 0 = segundos hasta poder reintentar."""
        now = time.monotonic()
        count, window_start = self._by_ip.get(ip, (0, now))

        if now - window_start >= self._window_seconds:
            # Ventana vencida: arranca una nueva.
            self._by_ip[ip] = (1, now)
            return 0.0

        if count >= self._max_requests:
            return self._window_seconds - (now - window_start)

        self._by_ip[ip] = (count + 1, window_start)
        return 0.0


# 30 requests/minuto por IP: generoso para uso normal (varios dispositivos
# del mismo usuario, incluidas las rutinas de Automation Engine que llaman
# tools en cadena), pero corta una ráfaga automatizada o un token filtrado.
chat_rate_limiter = RequestRateLimiter(max_requests=30, window_seconds=60.0)
