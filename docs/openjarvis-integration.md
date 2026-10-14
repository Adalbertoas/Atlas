# Influencia de OpenJarvis en ATLAS

ATLAS toma de OpenJarvis su enfoque **local-first** y modular, sin incorporar su orquestador completo: ATLAS ya tiene API, permisos, automatización, memoria y clientes propios. OpenJarvis se conserva como submódulo Apache-2.0 en `integrations/openjarvis` como referencia y futura fuente de integración.

## Voz local de alta calidad: Kokoro

El primer componente adaptado es el patrón de TTS por proveedor de OpenJarvis. ATLAS incorpora `KokoroProvider`, una opción neural local para reemplazar SAPI sin enviar las respuestas a un servicio de voz externo.

En `backend/.env`:

```env
TTS_PROVIDER=kokoro
KOKORO_VOICE=ef_dora
KOKORO_SPEED=1.0
```

Voces españolas disponibles habitualmente: `ef_dora`, `em_alex` y `em_santa`. La calidad y compatibilidad dependen de la instalación local de Kokoro/espeak-ng; en Windows, instalá espeak-ng antes del primer uso. SAPI sigue disponible con `TTS_PROVIDER=sapi` como alternativa.

## IA local con Ollama

ATLAS ahora también admite un modelo local por medio de Ollama:

```env
AI_PROVIDER=ollama
OLLAMA_BASE_URL=http://127.0.0.1:11434
OLLAMA_MODEL=qwen3:4b
```

Antes iniciá Ollama y descargá el modelo: `ollama pull qwen3:4b`. El adaptador soporta respuestas y llamadas a herramientas del API local; los permisos de ATLAS siguen actuando antes de toda acción del sistema.

## Siguientes componentes candidatos

- Perfiles de agente y catálogo de habilidades, adaptados al registro de herramientas y permisos de ATLAS.
- Briefing diario programado, usando automatizaciones, notificaciones y memoria existentes.
- Ejecución local-first con Ollama como proveedor de IA opcional.
- Auditoría de límites de datos para indicar con claridad qué servicios externos reciben audio, texto o imágenes.

No se copian credenciales, configuraciones personales ni dependencias de nube desde OpenJarvis. Revisá la licencia Apache-2.0 del submódulo antes de redistribuir cambios que incluyan código sustancial suyo.