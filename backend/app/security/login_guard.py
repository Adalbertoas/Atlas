"""Freno contra adivinar la contraseña: tras varios intentos fallidos desde una
misma dirección, el login se bloquea un rato para esa dirección.

Con ATLAS publicado en internet (Cloudflare Tunnel) todas las conexiones llegan
desde cloudflared en la propia PC, así que la dirección real del visitante se
toma de la cabecera CF-Connecting-IP que agrega Cloudflare.
"""
from __future__ import annotations

import threading
import time
from collections import defaultdict, deque

from fastapi import Request

MAX_FAILURES = 5
WINDOW_SECONDS = 15 * 60


class LoginGuard:
    def __init__(self, max_failures: int = MAX_FAILURES, window_seconds: int = WINDOW_SECONDS) -> None:
        self._max = max_failures
        self._window = window_seconds
        self._failures: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def _prune(self, key: str, now: float) -> deque[float]:
        attempts = self._failures[key]
        while attempts and now - attempts[0] > self._window:
            attempts.popleft()
        return attempts

    def retry_after(self, key: str, now: float | None = None) -> int:
        """Segundos que faltan para poder intentar de nuevo (0 = puede intentar)."""
        now = time.monotonic() if now is None else now
        with self._lock:
            attempts = self._prune(key, now)
            if len(attempts) < self._max:
                return 0
            return max(1, int(self._window - (now - attempts[0])) + 1)

    def failed(self, key: str, now: float | None = None) -> None:
        now = time.monotonic() if now is None else now
        with self._lock:
            self._prune(key, now).append(now)

    def succeeded(self, key: str) -> None:
        with self._lock:
            self._failures.pop(key, None)


def client_key(request: Request) -> str:
    forwarded = request.headers.get("cf-connecting-ip", "").strip()
    if forwarded:
        return forwarded
    return request.client.host if request.client else "desconocido"


login_guard = LoginGuard()
