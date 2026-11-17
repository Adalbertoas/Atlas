"""GET a servicios públicos con el mismo user agent y timeout que el resto de ATLAS."""
from __future__ import annotations

import requests

from app.web.client import TIMEOUT, USER_AGENT, WebError


def get(url: str, params: dict | None = None, timeout: float = TIMEOUT) -> requests.Response:
    try:
        response = requests.get(url, params=params, timeout=timeout, headers={"User-Agent": USER_AGENT})
    except requests.Timeout as exc:
        raise WebError("El servicio tardó demasiado en responder.") from exc
    except requests.RequestException as exc:
        raise WebError("No hay conexión con el servicio (¿sin internet?).") from exc
    if response.status_code >= 400:
        raise WebError(f"El servicio respondió con un error (HTTP {response.status_code}).")
    return response


def get_json(url: str, params: dict | None = None) -> dict:
    try:
        return get(url, params).json()
    except ValueError as exc:
        raise WebError("El servicio devolvió una respuesta inválida.") from exc
