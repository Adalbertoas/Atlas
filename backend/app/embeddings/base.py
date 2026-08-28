"""EmbeddingProvider: abstracción para convertir texto en vectores, mismo
patrón que AIProvider/VoiceProvider/SmartHomeProvider (app/*/base.py).

Se usa para búsqueda semántica de memoria (app/memory/service.py): guarda un
vector por cada MemoryEntry al crearla y compara por similitud de coseno
contra el vector de la consulta, en vez de depender solo de coincidencia
literal de texto (LIKE).
"""
from __future__ import annotations

from abc import ABC, abstractmethod


class EmbeddingProvider(ABC):
    @abstractmethod
    def embed(self, text: str) -> list[float]:
        """Devuelve el vector de embedding de `text`. Determinístico: el
        mismo texto siempre da el mismo vector (necesario para no tener que
        recalcular embeddings ya guardados)."""
        raise NotImplementedError
