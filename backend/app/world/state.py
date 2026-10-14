"""Última vista del mundo pedida por ATLAS, para que el dashboard la muestre.

Las tools de app.tools.world publican acá la vista que Gods Eye View devolvió;
el dashboard la consulta por GET /api/v1/world/view y se la pasa a su iframe.
En memoria de proceso, mismo criterio que PermissionManager: un solo usuario,
un solo proceso.
"""
from __future__ import annotations

import threading
import uuid
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class WorldViewUpdate:
    # uuid y no un contador: un contador vuelve a 1 al reiniciar el backend y
    # el dashboard abierto confundiría la vista nueva con una ya mostrada.
    id: str
    view: dict[str, Any]
    url: str | None
    summary: str


class WorldViewState:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._latest: WorldViewUpdate | None = None

    def publish(self, view: dict[str, Any], url: str | None, summary: str) -> WorldViewUpdate:
        update = WorldViewUpdate(id=uuid.uuid4().hex, view=view, url=url, summary=summary)
        with self._lock:
            self._latest = update
        return update

    def latest(self) -> WorldViewUpdate | None:
        with self._lock:
            return self._latest


def publish_result_view(state: WorldViewState, data: dict[str, Any], summary: str) -> bool:
    """Publica la vista que trae una respuesta de Gods Eye View, si trae alguna."""
    view = data.get("view")
    if not isinstance(view, dict):
        return False
    view = dict(view)
    # Las consultas devuelven el link dentro de la vista; show_in_gods_eye_view, al lado.
    url = view.pop("url", None) or data.get("url")
    state.publish(view, url, summary)
    return True


# Instancia única a nivel de proceso, compartida por las tools y la API.
world_view_state = WorldViewState()
