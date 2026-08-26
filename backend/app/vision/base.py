"""VisionProvider: interfaz de visión de ATLAS (sección 16 del prompt maestro).

Analizar imágenes/capturas de pantalla, identificar elementos visuales,
interpretar errores. Desacoplado del resto del sistema, mismo patrón que
AIProvider/SpeechToTextProvider/SmartHomeProvider.

Sin captura continua por defecto (sección 16): cada análisis es puntual,
bajo pedido explícito — nunca un stream ni un polling.
"""
from __future__ import annotations

from abc import ABC, abstractmethod


class VisionProvider(ABC):
    @abstractmethod
    def analyze(self, image_bytes: bytes, question: str | None = None) -> str:
        """Describe una imagen (o responde una pregunta puntual sobre ella).
        Incluye cualquier texto legible en la imagen (hace de OCR liviano
        sin necesitar un motor de OCR aparte — ver docs/architecture.md)."""
        raise NotImplementedError
