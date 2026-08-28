"""EmbeddingProvider real, local y gratis: modelo ONNX cuantizado vía
`fastembed`. Mismo criterio que Whisper (faster-whisper) para STT: capacidad
real sin API key, sin mandar datos a ningún servidor y sin depender de
internet una vez descargado el modelo.

Se eligió `fastembed` en vez de `sentence-transformers`: este último arrastra
PyTorch completo (+600MB) solo para correr un modelo chico; fastembed corre
el mismo tipo de modelo (all-MiniLM-L6-v2 por defecto) sobre onnxruntime,
~90MB. El import es diferido (como en tuya_provider.py): quien deje
EMBEDDING_PROVIDER=mock no necesita tener la librería instalada.
"""
from __future__ import annotations

from app.embeddings.base import EmbeddingProvider


class FastEmbedProvider(EmbeddingProvider):
    def __init__(self, model_name: str) -> None:
        from fastembed import TextEmbedding

        # La primera vez descarga el modelo (~90MB) a un caché local; después
        # corre offline. Instanciar el modelo es lo caro, por eso se hace una
        # sola vez acá y no en cada llamada a embed().
        self._model = TextEmbedding(model_name=model_name)

    def embed(self, text: str) -> list[float]:
        # TextEmbedding.embed() es un generador pensado para lotes; para un
        # solo texto alcanza con tomar el primer resultado.
        (vector,) = self._model.embed([text])
        return vector.tolist()
