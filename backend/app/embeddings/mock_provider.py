"""EmbeddingProvider para tests/desarrollo: no descarga ningún modelo.

No es aleatorio: usa un hash de palabras determinístico para que dos textos
parecidos ("le gusta el café" / "le gusta el café negro") den vectores
parecidos y dos textos distintos den vectores distintos — suficiente para
probar que el ranking por similitud funciona, sin bajar ~90MB de modelo en
cada corrida de tests ni depender de tener `fastembed` instalado.
"""
from __future__ import annotations

import hashlib
import math

from app.embeddings.base import EmbeddingProvider

_DIMENSIONS = 32


class MockEmbeddingProvider(EmbeddingProvider):
    def embed(self, text: str) -> list[float]:
        vector = [0.0] * _DIMENSIONS
        words = text.lower().split()
        if not words:
            return vector
        for word in words:
            digest = hashlib.sha256(word.encode("utf-8")).digest()
            for i in range(_DIMENSIONS):
                # Mapeado a [-1, 1], no [0, 1]: con componentes solo
                # positivos, cualquier par de vectores queda con similitud
                # de coseno alta "gratis" (todos apuntan hacia el mismo
                # octante), aunque las palabras no tengan nada en común. Con
                # signo, palabras no relacionadas tienden a cancelarse.
                vector[i] += (digest[i % len(digest)] / 127.5) - 1.0
        norm = math.sqrt(sum(v * v for v in vector)) or 1.0
        return [v / norm for v in vector]
