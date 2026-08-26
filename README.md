# ATLAS

Asistente personal de inteligencia — un sistema modular tipo JARVIS, construido
desde cero, original, no un chatbot.

Estado actual: **las 9 fases del prompt maestro están completas** (núcleo,
memoria/personalidad/Event Bus, voz + wake word, control de Windows +
cliente de escritorio, Smart Home, Automation Engine, login + app móvil
como PWA, Visión, y el dashboard visual), todas validadas en vivo con
Claude real. Ver `docs/architecture.md` para el detalle fase por fase y
`docs/pending-manual-tests.md` para lo que falta confirmar en persona
(sobre todo desde el celular real).

## Qué incluye

**Fase 1 (núcleo):**
- API en FastAPI con el flujo completo: `Chat → Orchestrator → AIProvider →
  Tool Calling → Permission Manager → Ejecución → Memoria/Audit → Respuesta`.
- `AIProvider` desacoplado (`app/ai/`): `AnthropicProvider` (Claude) y
  `MockProvider` (sin costo, para desarrollo/tests).
- Sistema de herramientas (`app/tools/`) con 7 tools base:
  `get_system_info`, `get_current_time`, `open_application`, `list_files`,
  `search_files`, `create_memory`, `search_memory`.
- Sistema de permisos por nivel de riesgo (`app/security/permissions.py`):
  `READ_ONLY`, `LOW_RISK`, `MEDIUM_RISK`, `HIGH_RISK`, `CRITICAL`. Las
  acciones de riesgo medio o mayor piden confirmación antes de ejecutarse.
- `AuditLog` (`app/security/audit.py`): registra cada ejecución de tool.
- Memoria personal (`app/memory/`): crear, listar, buscar, olvidar.

**Fase 2 (agregado sobre lo anterior):**
- Memoria de conversación multi-turno (`app/memory/conversation_service.py`):
  ATLAS recuerda los mensajes previos de una misma `conversation_id`.
- Personalidad configurable (`app/personality/`): tono, nivel de detalle e
  instrucciones extra, vía `GET/PUT /api/v1/settings/personality`.
- Event Bus interno (`app/events/bus.py`): pub/sub en memoria de proceso,
  publica `USER_COMMAND` en cada mensaje — base para Automation
  Engine/Smart Home en fases futuras.

**Fase 3 (voz, agregado sobre lo anterior):**
- `SpeechToTextProvider` / `TextToSpeechProvider` / `VoiceActivationProvider`
  desacoplados (`app/voice/`), mismo patrón que `AIProvider`.
- STT real: Whisper local vía `faster-whisper` (gratis, sin internet).
- TTS real: voces de Windows vía `pyttsx3` (gratis, sin internet).
- Endpoints `POST /api/v1/voice/transcribe` y `POST /api/v1/voice/speak`.
- Modo Push-to-Talk (`PushToTalkProvider`). Wake word ("Hey ATLAS") queda
  para una fase posterior — ver `docs/architecture.md`.
- Script de demo por consola `backend/scripts/voice_chat_demo.py`: habla con
  ATLAS usando el micrófono/parlantes de tu PC.

**Fase 4 (control de Windows + cliente de escritorio):**
- 4 tools nuevas: `list_processes`, `close_application`, `open_file`,
  `control_media` (sección 12).
- `GET /api/v1/system/status`: CPU/RAM/disco directo, sin pasar por la IA.
- **Cliente de escritorio real** (`desktop/`): ventana en Python +
  `customtkinter` — chat, botón de voz (push-to-talk), diálogo de
  confirmación para acciones de riesgo medio/alto, y panel de estado del
  sistema en vivo. Habla con el backend por la misma API que ya se probó.

**Fase 5 (Smart Home + Home Assistant):**
- `SmartHomeProvider` desacoplado (`app/smart_home/`): `HomeAssistantProvider`
  (real, habla con la API REST de HA) y `MockSmartHomeProvider` (para tests).
- Habitaciones propias de ATLAS (`Room`, asignación de dispositivos vía
  `PUT /api/v1/devices/{id}/room`) — independientes de las áreas de HA.
- Tools: `list_devices`, `set_device_state` (riesgo dinámico según el tipo
  de dispositivo: luz = LOW_RISK, cerradura = CRITICAL, cámara = HIGH_RISK),
  `control_room` (acciones masivas, solo tipos seguros — nunca cerraduras,
  cámaras, sensores ni climatización en bloque).
- `GET /api/v1/devices`, `GET/POST /api/v1/rooms`: directo, sin pasar por
  la IA.

**Wake word "Atlas" (agregado sobre la Fase 4, cliente de escritorio):**
- Escucha continua activada automáticamente al abrir el cliente (pedido
  explícito del usuario — no queda apagada por defecto como el resto de las
  capturas de cámara/audio del proyecto). Botón "👂 Escucha" para
  apagarla/prenderla manualmente.
- Reutiliza Whisper (sin motor de wake-word dedicado): buffer de audio
  deslizante + filtro de energía + `/api/v1/voice/transcribe` con idioma
  forzado a español. Solo reacciona si "Atlas" aparece entre las primeras
  palabras transcritas (evita disparos por conversaciones de fondo).
- `desktop/atlas_desktop/wake_word.py`, 55 tests backend + 15 desktop.

**Fase 6 (Automation Engine):**
- Rutinas con acciones (reutilizan las tools existentes) y triggers por
  horario o por estado de otro dispositivo. Tool `run_routine` para
  ejecutarlas por voz/chat ("ejecuta mi rutina de dormir").
- **Ninguna automatización ejecuta nunca una acción que requiera
  confirmación** (cerraduras, cámaras) — se salta y publica una
  notificación en el Event Bus, sea que la haya disparado un horario, otro
  dispositivo, o el propio usuario por voz.
- `GET/POST /api/v1/automations`, `POST /api/v1/automations/{id}/run`,
  `DELETE /api/v1/automations/{id}`.
- 63 tests backend.

**Fase 7 (App móvil como PWA + autenticación):**
- **Login real activado**: `POST /api/v1/auth/login` (JWT), sistema de un
  solo usuario (`ATLAS_PASSWORD` en `.env`). Todos los endpoints salvo
  `/system/health` y `/auth/login` ahora exigen `Authorization: Bearer`.
  El cliente de escritorio se actualizó para loguearse solo al arrancar.
- **Cliente móvil** (`mobile/`): PWA en HTML/CSS/JS vanilla (sin Node/npm),
  instalable en el celular. Chat + voz (grabación desde el navegador),
  dispositivos, rutinas, notificaciones y memoria. Server estático propio
  (`mobile/serve.py`) escuchando en la red local.
- Notificaciones persistidas (`GET/PATCH /api/v1/notifications`): cierra el
  círculo con la Fase 6 — cuando una automatización salta una acción
  riesgosa, ahora queda una notificación real que ver en la app.
- CORS habilitado (necesario para que la PWA, en otro puerto, pueda hablar
  con la API).
- 75 tests backend + 17 desktop.

**Fase 8 (Visión):**
- `VisionProvider` desacoplado (`app/vision/`): `AnthropicVisionProvider`
  (real, Claude es multimodal) y `MockVisionProvider` (para tests).
- Tool `analyze_screenshot` (`HIGH_RISK`, igual que "acceder a una cámara"
  en la sección 5 — siempre pide confirmación): captura la pantalla de la
  PC y la describe. Sin motor de OCR aparte — Claude ya lee texto de la
  imagen como parte de la respuesta.
- `POST /api/v1/vision/analyze`: analiza una imagen ya subida (foto desde
  el celular, captura manual) sin pasar por tool calling.
- Botón "📷 Pantalla" en el escritorio y "📷" (subir/sacar foto) en la PWA.
- 81 tests backend.

**Fase 9 (Dashboard / interfaz futurista) — última fase del prompt maestro:**
- Tercer cliente, `dashboard/`: HTML/CSS/JS vanilla (mismo criterio que
  `mobile/`, sin build), pensado para pantalla ancha de PC. Barra lateral de
  navegación, orbe de voz con visualizador de audio real (Web Audio API,
  `AnalyserNode` — no una animación falsa), anillos de CPU/RAM/Disco en CSS
  puro, widgets de dispositivos/actividad, y las mismas vistas de
  dispositivos/automatizaciones/notificaciones/memoria que la PWA.
- Todo lo que se muestra sale de datos reales de la API ya existente — no
  se inventaron widgets con datos falsos.
- Nuevo `GET /api/v1/system/activity`: expone el `AuditLog` (Fase 1) que
  hasta ahora solo vivía en la base de datos, sin forma de consultarlo.
- Identidad visual propia (fondo oscuro, acento cian), consistente entre
  `mobile/` y `dashboard/`, sin parecerse a Iron Man/Marvel.
- 85 tests backend.

## Estructura

```
atlas/
├── backend/
│   ├── app/
│   │   ├── api/v1/        # endpoints REST (chat, memory, tools, system)
│   │   ├── ai/            # AIProvider + implementaciones
│   │   ├── core/          # database, logging, Orchestrator (el cerebro)
│   │   ├── memory/        # modelo, schema, servicio de memoria
│   │   ├── tools/         # base, registry, y las tools por categoría
│   │   ├── security/      # permisos y auditoría
│   │   ├── schemas/       # Pydantic de la API
│   │   ├── config.py      # Settings desde .env
│   │   └── main.py        # FastAPI app factory
│   ├── tests/
│   ├── requirements.txt
│   ├── .env.example
│   └── run.py             # `python run.py` = levantar el servidor
├── docs/
│   └── architecture.md    # decisiones arquitectónicas
├── .gitignore
└── README.md
```

```
desktop/                   # cliente de escritorio (Python + customtkinter, Fase 4)
├── atlas_desktop/
└── run.py

mobile/                    # cliente móvil PWA (HTML/CSS/JS vanilla, Fase 7)
├── index.html, app.js, styles.css
└── serve.py

dashboard/                 # dashboard visual para PC (HTML/CSS/JS vanilla, Fase 9)
├── index.html, app.js, styles.css
└── serve.py
```

## Cómo ejecutar ATLAS

Requisitos: Python 3.12+ (probado con 3.13).

```powershell
cd backend
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt

copy .env.example .env
# Edita .env: por defecto AI_PROVIDER=mock (no necesitas API key para probar).
# Para usar Claude de verdad: AI_PROVIDER=anthropic y ANTHROPIC_API_KEY=tu_key

python run.py
```

El servidor queda en `http://127.0.0.1:8000`. Documentación interactiva
(Swagger) en `http://127.0.0.1:8000/docs`.

## Configurar variables de entorno

Copia `backend/.env.example` a `backend/.env` (nunca subas `.env` al
repositorio — ya está en `.gitignore`). Variables relevantes en V1:

| Variable | Uso en V1 |
|---|---|
| `AI_PROVIDER` | `mock` (sin costo) o `anthropic` |
| `ANTHROPIC_API_KEY` | solo si `AI_PROVIDER=anthropic` |
| `DATABASE_URL` | por defecto SQLite (`sqlite:///./atlas.db`) |
| `REDIS_URL`, `JWT_SECRET`, `SMART_HOME_*` | reservadas para fases futuras, no se usan todavía |

## Cómo probarlo

```powershell
cd backend
.venv\Scripts\Activate.ps1
pytest -v
```

Prueba manual rápida (con el servidor corriendo y `AI_PROVIDER=mock`):

```powershell
curl -X POST http://127.0.0.1:8000/api/v1/chat -H "Content-Type: application/json" -d "{\"message\": \"que hora es?\"}"
curl -X POST http://127.0.0.1:8000/api/v1/chat -H "Content-Type: application/json" -d "{\"message\": \"abre vscode\"}"
# devuelve requires_confirmation=true y un confirmation_id; luego:
curl -X POST http://127.0.0.1:8000/api/v1/chat/confirm -H "Content-Type: application/json" -d "{\"confirmation_id\": \"<id>\", \"approve\": true}"
```

## Cómo probar la voz

```powershell
# En .env: STT_PROVIDER=whisper, TTS_PROVIDER=sapi (por defecto ambos están
# en "mock" para no obligar a instalar/descargar nada solo para correr tests).
python run.py
# en otra terminal:
python scripts/voice_chat_demo.py
```
Enter para grabar, Enter de nuevo para terminar, y ATLAS te responde por voz.
La primera vez que uses Whisper se descarga el modelo (~150 MB para "base").

## Cómo probar el cliente de escritorio

```powershell
# Terminal 1: backend
cd backend
python run.py

# Terminal 2: cliente de escritorio
cd desktop
pip install -r requirements.txt   # si no reutilizas el venv de backend/
python run.py
```

Prueba: mandar un mensaje de texto, usar "🎙️ Hablar" (clic para empezar a
grabar, clic de nuevo para detener y enviar), pedir algo que requiera
confirmación (ej. "abre la calculadora") y confirmar/cancelar desde el
diálogo, y ver el panel CPU/RAM/Disco actualizarse solo cada 3 segundos.

> ⚠️ Si editas el backend mientras está corriendo, el `--reload` de uvicorn
> puede *decir* que recargó sin hacerlo de verdad en este entorno (ver
> `docs/architecture.md`, Fase 4). Si un cambio no se refleja, reinicia el
> servidor por completo antes de asumir que el código está mal.

## Cómo conectar tu Home Assistant real

En `.env`: `SMART_HOME_PROVIDER=home_assistant`, `SMART_HOME_URL` (ej.
`http://192.168.1.x:8123`) y `SMART_HOME_TOKEN` (Long-Lived Access Token,
se genera desde tu perfil de usuario en HA). Por defecto usa
`SMART_HOME_PROVIDER=mock` (4 dispositivos de prueba, sin hardware real).

## Cómo configurar el login (Fase 7)

En `backend/.env`: `ATLAS_PASSWORD` (elegí una contraseña real) y generá un
`JWT_SECRET` real, ej.:

```powershell
python -c "import secrets; print(secrets.token_hex(32))"
```

El cliente de escritorio necesita la misma contraseña en `desktop/.env`
(`ATLAS_PASSWORD=...`, copiá `desktop/.env.example`) para loguearse solo al
arrancar.

## Cómo usar el cliente móvil (PWA)

```powershell
# Con el backend ya corriendo:
cd mobile
python serve.py
```

Te va a mostrar dos URLs: una para abrir desde la misma PC
(`http://127.0.0.1:5173`) y otra con tu IP local para abrir desde el
celular (misma WiFi que la PC). Desde el navegador del celular podés
"Agregar a pantalla de inicio" para que quede como un ícono más.

### HTTPS local (necesario para cámara/micrófono desde el celular)

El micrófono y la cámara del navegador solo funcionan en "contextos
seguros" — HTTPS o `localhost`. Para que el celular (que no es
`localhost`) pueda usarlos, generá un certificado autofirmado una sola vez:

```powershell
python scripts/generate_dev_cert.py 192.168.1.50   # tu IP local, la que te muestra serve.py
```

Con `certs/dev-cert.pem` y `certs/dev-key.pem` presentes, tanto
`backend/run.py` como `mobile/serve.py` levantan solos en HTTPS/WSS. La
primera vez que el celular (o cualquier navegador) entra a esa IP, avisa
que el certificado no es de confianza — elegí "Visitar de todas formas"
(es tu propio certificado, autofirmado, no hay nada raro). El
`desktop/` y el `dashboard/` (que corren en la misma PC que el backend)
detectan el certificado solos y validan contra él en vez de desactivar la
verificación TLS.

⚠️ Con HTTPS activo, `backend/run.py` deja de escuchar en `http://`, así
que cualquier cliente (desktop, dashboard, curl) que le apunte con
`http://` en vez de `https://` va a fallar en silencio con un error de
conexión — es la causa más común de "no conecta"/"no arranca" si acabás de
generar el certificado.

## Cómo usar el control por gestos (celular controla el mouse de la PC)

Pestaña "Gestos" dentro de la PWA (`mobile/`, sección de arriba) — sin
cliente aparte. Requiere HTTPS (ver arriba) porque usa la cámara. El
celular tiene que quedar apoyado/fijo, viendo tus dos manos:

- **Mano derecha** (la que ve la cámara): el nudillo del índice mueve el
  cursor de la PC; juntar el pulgar y el índice (pellizco) hace clic o
  arrastra.
- **Mano izquierda**: puño cerrado, moviéndolo arriba/abajo, hace scroll.

La detección de manos corre en el navegador (MediaPipe Tasks Vision,
cargado desde CDN — único recurso externo del proyecto) y solo manda
coordenadas por WebSocket (`/api/v1/gestures/stream`), nunca video. El
backend mueve el mouse real de esa PC con `pyautogui`. No pasa por el
Permission Manager ni por la IA: es entrada de bajo nivel, como un mouse
físico. La cámara se apaga sola al salir de la pestaña.

## Cómo usar el dashboard (Fase 9)

```powershell
# Con el backend ya corriendo:
cd dashboard
python serve.py
```

Abre `http://127.0.0.1:5174` — pensado para pantalla ancha de PC (no para
celular, para eso está la PWA de `mobile/`). Barra lateral con Inicio,
Dispositivos, Automatizaciones, Notificaciones, Memoria y Actividad; el
orbe central tiene un visualizador de audio real mientras grabás o ATLAS
te responde por voz.

## Qué queda pendiente / ideas a futuro

Las 9 fases del prompt maestro están completas, más el control por gestos
(fuera del prompt original, agregado a pedido — ver arriba). Lo que queda
documentado como pendiente, no implementado a medias:

- Push real (Web Push/VAPID) para notificaciones — hoy son "en la app", no
  push del sistema operativo; requeriría HTTPS.
- Acceso remoto real (fuera de la WiFi de casa) — hoy la PWA solo funciona
  en la misma red local que el backend.
- Más cobertura de tool calling (hoy se resuelve un tool_call a la vez;
  suficiente para las tools actuales, pero limitante si el modelo pide
  varias tools en un mismo turno).
- Posible reescritura del cliente de escritorio en C#/.NET, o de la PWA a
  Flutter nativo, si alguno resulta insuficiente más adelante.

## Decisiones arquitectónicas de esta entrega

Ver `docs/architecture.md` para el detalle y el porqué de: SQLite en vez de
PostgreSQL por ahora, sin Docker, y el diseño de `AIProvider` pensado para
BYOK (cada usuario con su propia key de Claude) en una futura versión
pública.
