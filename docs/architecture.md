# ATLAS — Decisiones arquitectónicas (V1)

## Por qué SQLite en vez de PostgreSQL en esta entrega

El prompt maestro pide PostgreSQL como base de datos principal. Se optó por
SQLite en la V1 porque:

- Cero configuración: no depende de tener un servidor Postgres corriendo
  para simplemente probar el flujo de chat + tools.
- Todo el acceso a datos pasa por SQLAlchemy ORM (`app/core/database.py`,
  `app/memory/models.py`, `app/security/audit.py`). Migrar a Postgres más
  adelante es cambiar `DATABASE_URL` y el driver instalado — no reescribir
  modelos ni servicios.

Cuando el sistema necesite escrituras concurrentes reales (múltiples
clientes, Fase 4+) o tipos de datos específicos de Postgres, se migra sin
tocar la capa de negocio.

## Por qué no hay Redis todavía

El prompt maestro lo pide "cuando sea necesario" para sesiones, caché,
tareas y eventos. Ninguno de esos casos existe aún en V1: no hay sesiones de
usuario (no hay login), no hay tareas en background, y el Event Bus todavía
no se implementó (queda para Fase 2). Se agrega cuando el primero de esos
casos aparezca, en vez de cargar una dependencia sin uso real.

## Por qué no hay autenticación (JWT) todavía

V1 corre como un solo proceso, para un solo usuario, en la propia máquina —
no hay cliente remoto que necesite autenticarse contra el servidor. El
prompt maestro reserva `JWT_SECRET` para cuando exista un cliente que se
conecte por red (Windows Fase 4, móvil Fase 7); implementarlo antes sería
complejidad sin consumidor. La variable ya está en `.env.example` para no
tener que rediseñar la configuración cuando llegue el momento.

## Diseño de `AIProvider` pensado para BYOK futuro

El usuario planea que ATLAS sea eventualmente una aplicación pública donde
cada persona use su propia suscripción/API key de Claude (bring-your-own-key).
Por eso:

- `AnthropicProvider.__init__` recibe `api_key` como parámetro explícito, no
  lo lee de `os.environ` internamente. Quien lo instancia (hoy:
  `app/api/deps.py`, con la key de `.env`) decide de dónde sale la key.
- Cuando exista un modelo multi-usuario, `deps.py` (o su sucesor) puede
  construir un `AnthropicProvider` por request/usuario con la key guardada
  (cifrada) en su perfil, sin tocar `AnthropicProvider` ni el `Orchestrator`.
- Por eso mismo `AIProvider` es una interfaz abstracta desde el día uno: el
  Orchestrator y las tools no saben qué proveedor están usando.

## Permission Manager: confirmaciones en memoria de proceso

Las confirmaciones pendientes (`PendingConfirmation`) se guardan en un dict
en memoria dentro de `PermissionManager`, no en la base de datos. Es
suficiente para V1 (un solo proceso, un solo worker de uvicorn). Si el
backend escala a múltiples workers/procesos, este store debe moverse a Redis
para que una confirmación creada en un worker pueda resolverse en otro.

## Por qué `open_application` usa un allowlist y no ejecución arbitraria

Regla explícita de la sección 12 del prompt maestro: nunca ejecución
arbitraria de comandos por defecto. `APPLICATION_ALLOWLIST` en
`app/tools/computer/open_application.py` mapea alias fijos a comandos
conocidos; cualquier alias fuera de esa lista se rechaza antes de tocar
`subprocess`. Extender qué aplicaciones se pueden abrir significa editar
esa lista explícitamente, nunca aceptar una ruta libre del usuario o del
modelo.

## Por qué el flujo de confirmación es "pedir → aprobar/cancelar" y no
"ejecutar con rollback"

Para acciones como abrir una aplicación no existe un "deshacer" limpio, así
que el diseño sigue el ejemplo literal del prompt maestro (sección 5): la
tool jamás se ejecuta hasta que el usuario confirma explícitamente vía
`POST /api/v1/chat/confirm`. Esto se generaliza igual para `HIGH_RISK` y
`CRITICAL` cuando se agreguen tools de esos niveles (cámara, cerraduras) en
fases posteriores — no hace falta cambiar el mecanismo, solo asignarles el
`risk_level` correspondiente.

## Bug corregido: tool_use no se reenviaba al historial (Anthropic)

Al probar V1 con una key real de Anthropic apareció un error real: la API
rechazaba el segundo turno de cada tool call con `unexpected tool_use_id
found in tool_result blocks`. Causa: el Orchestrator guardaba el resultado
de la tool (`role="tool"`) pero nunca reenviaba el bloque `tool_use` que el
modelo generó para pedirla — Anthropic exige que ese bloque esté presente en
el turno anterior al `tool_result`. Se agregó `AIMessage.tool_calls` (para
mensajes `role="assistant"`) y el Orchestrator ahora agrega ese mensaje antes
de ejecutar la tool. Cubierto por `tests/test_chat_api.py` (con
`MockProvider`) y verificado manualmente en vivo con Claude real.

## Qué no se implementó a propósito en V1 (Fase 1) — ya resuelto en Fase 2

- Personalidad configurable, Event Bus y memoria de conversación multi-turno
  quedaron pendientes explícitamente en Fase 1. Los tres se implementaron en
  Fase 2 (ver sección siguiente) sin tocar el resto del sistema — confirma
  que dejarlos como "TODO" documentado en vez de código vacío fue la
  decisión correcta: se agregaron limpio, sin refactors grandes.

## Fase 2: memoria de conversación, personalidad y Event Bus

- **Memoria de conversación** (`app/memory/models.py::ConversationMessage`,
  `app/memory/conversation_service.py`): se guarda como tabla separada de
  `MemoryEntry` a propósito — son conceptos distintos (sección 6: "qué se
  dijo" vs "qué se debe recordar"). El Orchestrator carga los últimos 20
  mensajes de la `conversation_id` (generada automáticamente si el cliente
  no manda una) y los antepone como contexto real; el estado de las tools
  intermedias (tool_use/tool_result) no se persiste, solo los turnos
  user/assistant, para no ensuciar el historial con ruido técnico.
- **Personalidad configurable** (`app/personality/`): una sola fila
  (`PersonalityProfile`) en V1 — no hay multi-usuario todavía. El
  `SYSTEM_PROMPT` fijo de Fase 1 se reemplazó por
  `build_system_prompt(profile)`, construido dinámicamente en cada mensaje.
  Expuesto vía `GET/PUT /api/v1/settings/personality`.
- **Event Bus** (`app/events/bus.py`): pub/sub síncrono en memoria de
  proceso — mismo criterio que Redis en Fase 1: se implementa la versión más
  simple que resuelve el caso de uso actual (un subscriber de logging que
  prueba el mecanismo) y se migra a Redis pub/sub cuando haya multi-worker o
  consumidores reales (Automation Engine en Fase 6, Smart Home en Fase 5).
  El Orchestrator publica `USER_COMMAND` en cada mensaje recibido.
- Validado en vivo con Claude real: continuidad de contexto entre turnos
  (`"me llamo Alex"` → `"¿cómo me llamo?"`), cambio de tono al actualizar
  `verbosity`, y el evento `USER_COMMAND` apareciendo en el log del proceso.

## Fase 3: voz (Whisper local + voces de Windows)

- `app/voice/base.py` define `SpeechToTextProvider`, `TextToSpeechProvider`
  y `VoiceActivationProvider`, igual patrón que `AIProvider`. Las
  implementaciones reales (`WhisperLocalProvider`, `WindowsSapiProvider`)
  se importan de forma perezosa dentro de `app/api/deps.py` — así
  `faster-whisper`/`pyttsx3` solo se cargan si `STT_PROVIDER=whisper` /
  `TTS_PROVIDER=sapi` están activos, y los tests (que usan Mock por defecto)
  no pagan el costo de importarlos.
- `/voice/transcribe` y `/voice/speak` son endpoints separados, no un único
  pipeline "voz completa". El cliente (hoy: `scripts/voice_chat_demo.py`;
  después: el cliente Windows de Fase 4) orquesta transcribe → `/chat` (ya
  existente) → speak. Evita duplicar la lógica del Orchestrator en una
  segunda ruta de código.
- **VoiceActivationProvider**: solo se implementó `PushToTalkProvider`
  (trivial: el cliente decide cuándo grabar). `WAKE_WORD` ("Hey ATLAS")
  necesita escucha continua de audio + un modelo de detección de palabra
  clave (ej. openWakeWord/Porcupine) corriendo en el cliente, no en el
  servidor — no tiene sentido implementarlo hasta que exista un cliente de
  escritorio real (Fase 4) que pueda mantener un stream de audio abierto.
- **Bug real encontrado y corregido**: `pyttsx3` (driver SAPI5, vía
  `comtypes`) escribe archivos de caché dentro de `.venv/` la primera vez
  que se usa. El `--reload` de uvicorn vigilaba todo `backend/` por
  defecto, así que la primera llamada a `/voice/speak` disparaba un
  reinicio del servidor a mitad de la request. Se corrigió acotando el
  watcher a `reload_dirs=["app"]` en `backend/run.py`.
- Validado en vivo: TTS real generando un WAV válido y audible (voces de
  Windows), Whisper local descargando su modelo y transcribiendo
  correctamente, y una prueba de round-trip completa (texto → voz → texto)
  a través de los dos endpoints reales.

## Fase 4: control de Windows + cliente de escritorio

- 4 tools nuevas (`list_processes`, `close_application`, `open_file`,
  `control_media`), mismo patrón `Tool`/`RiskLevel` que las anteriores.
  `get_system_info` se refactorizó para extraer `collect_system_info()`,
  reutilizada también por el nuevo `GET /api/v1/system/status` (métricas
  directas, sin pasar por la IA — necesario para que el cliente de
  escritorio pueda sondear CPU/RAM cada pocos segundos sin gastar tokens).
- **Bug real encontrado y corregido**: `close_application` con
  `process_name="calculadora"` fallaba siempre, porque la Calculadora de
  Windows corre como proceso `CalculatorApp.exe` — `calc.exe` es solo un
  stub que la lanza (app UWP). Se agregó `PROCESS_NAME_ALIASES` (mismo
  espíritu que el allowlist de `open_application`) para resolver alias
  conversacionales a nombres de proceso reales.
- **Problema de entorno encontrado (no es un bug de ATLAS)**: el
  `--reload`/`WatchFiles` de uvicorn en esta máquina logueaba "Reloading..."
  pero **no reiniciaba realmente el proceso** — el servidor seguía sirviendo
  el código viejo indefinidamente después de una edición, lo que hizo
  parecer que el fix de `close_application` no funcionaba cuando en
  realidad sí. Se confirmó con un reinicio limpio del proceso. Lección para
  el resto del desarrollo: si un cambio no se refleja en pruebas en vivo
  pese a que los tests automatizados pasan, reiniciar el servidor por
  completo (matar el proceso y volver a correr `python run.py`) antes de
  asumir que el código está mal.
- Cliente de escritorio (`desktop/`): Python + `customtkinter`, no C#/.NET
  — decisión explícita del usuario para iterar rápido reutilizando todo lo
  ya construido; se reevalúa si hace falta "control profundo" que Python no
  dé. Es un cliente puro: solo habla con la API HTTP existente
  (`/chat`, `/chat/confirm`, `/voice/*`, `/system/status`), sin lógica de
  negocio propia — mantiene la arquitectura cliente-servidor de la
  sección 2.
- Validado: 44 tests (en ese momento) de backend + 8 de `desktop/tests/test_api_client.py`
  (con `requests` interceptado, sin servidor real). En vivo: `/system/status`
  respondiendo cada 3s sin pasar por la IA, ventana de escritorio abierta
  sin errores. **Pendiente de confirmar con el usuario en persona** (no
  verificable desde esta sesión): que el layout se vea bien, que la voz con
  su propia voz (no la sintética usada en las pruebas) transcriba
  correctamente, que el TTS se escuche por sus parlantes, y el diálogo de
  confirmación end-to-end en la GUI — checklist en
  `docs/pending-manual-tests.md`.

## Fase 5: Smart Home + Home Assistant

- `SmartHomeProvider` (`app/smart_home/base.py`) sigue el mismo patrón que
  `AIProvider`/`SpeechToTextProvider`: `HomeAssistantProvider` (real, REST)
  y `MockSmartHomeProvider` (en memoria, para tests) intercambiables por
  `SMART_HOME_PROVIDER` en `.env`.
- **Habitaciones son un concepto propio de ATLAS**, no importado del
  registro de áreas de Home Assistant: la API REST simple de HA no expone
  áreas sin usar su API de WebSocket (más compleja). `Room` y
  `SmartDeviceMeta` (`app/smart_home/models.py`) viven en la DB de ATLAS; el
  usuario asigna cada dispositivo a una habitación vía
  `PUT /api/v1/devices/{id}/room`. El **estado** de un dispositivo nunca se
  cachea — siempre se consulta en vivo al provider.
- **Riesgo dinámico por tipo de dispositivo**: se agregó
  `Tool.resolve_risk_level(params)` (`app/tools/base.py`), con default que
  devuelve el `risk_level` estático de siempre (no rompe ninguna tool
  existente). `SetDeviceStateTool` lo sobreescribe: busca el dispositivo
  objetivo y devuelve `CRITICAL` para `LOCK`, `HIGH_RISK` para `CAMERA`,
  `LOW_RISK` para el resto — y `MEDIUM_RISK` si no pudo identificar el
  dispositivo (nunca asume que algo no verificado es de bajo riesgo). El
  Orchestrator llama a este método en vez de leer `tool.risk_level` directo.
- **`control_room` restringido a tipos seguros por diseño**: la tool filtra
  a `ROOM_BULK_SAFE_TYPES` (Light/Switch/Plug/Fan/TV) antes de tocar nada —
  Lock/Camera/Sensor/Climate quedan excluidos de cualquier acción masiva,
  sin excepción y sin depender de que el usuario confirme bien.
- Validado en vivo con Claude real (`MockSmartHomeProvider`, sin HA
  conectado todavía): "enciende la luz de la sala" auto-ejecuta,
  "desbloquea la puerta principal" pide confirmación CRITICAL, y "apaga
  todo en la oficina" solo afectó el enchufe de esa habitación — la
  cerradura y el termostato quedaron intactos pese a estar en la misma
  habitación en la prueba.
- **Pendiente**: conectar la instancia real de Home Assistant del usuario
  (`SMART_HOME_PROVIDER=home_assistant` + URL/token en `.env`) — ver
  `docs/pending-manual-tests.md`.

## Wake word "Atlas" (cliente de escritorio)

Construido en vivo, iterando directamente con el usuario probando en su PC
— quedan documentados los bugs reales encontrados en el camino porque
varios no son obvios y podrían repetirse:

- **Bug real: crash silencioso por encoding.** Un `print()` de depuración
  con texto transcrito (que a veces incluía caracteres que la consola de
  Windows —cp1252— no puede representar) lanzaba `UnicodeEncodeError` y
  mataba el hilo de escucha en silencio, sin ningún error visible en la UI.
  Corregido reconfigurando `stdout`/`stderr` a UTF-8 en `desktop/run.py`
  (`errors="replace"`) — protege cualquier print/traceback futuro, no solo
  este caso puntual. Además, el loop de `WakeWordListener._run` ahora
  atrapa cualquier excepción inesperada y sigue escuchando en vez de morir.
- **Bug real: bloques de grabación fijos cortaban la palabra.** La primera
  versión grababa bloques de 2.5s pegados uno tras otro (`sd.rec()`
  secuencial); "Atlas" a veces quedaba partido justo en el límite entre dos
  bloques, y Whisper transcribía fragmentos irreconocibles (llegó a
  transcribir en alfabeto cirílico). Se reemplazó por un `sd.InputStream`
  continuo con buffer deslizante (`collections.deque` de tamaño fijo) que
  se revisa cada segundo — la palabra completa siempre cae dentro de alguna
  ventana.
  - Sobre esto se ajustó también el umbral de silencio: 300 de RMS
    resultó demasiado bajo (el ruido ambiente de una habitación normal ya
    llega a ~800 y disparaba transcripciones alucinadas por Whisper sobre
    ruido de fondo); se subió a 1000, documentado como un valor que puede
    necesitar ajuste según el micrófono/ambiente de cada quien.
- **Bug real: detección de idioma automática nada confiable en clips
  cortos.** Sin forzar idioma, Whisper detectó español, inglés, italiano y
  hasta transcribió una vez en alfabeto cirílico ruso para el mismo tipo de
  audio corto y ambiguo. `POST /api/v1/voice/transcribe` ahora acepta un
  parámetro `language` (default `"es"`) — se puede pasar `None` para volver
  a la detección automática si hiciera falta en el futuro (ej. un usuario
  que hable otro idioma).
- **Decisión de producto, no bug**: el usuario pidió explícitamente que la
  escucha arrancara sola al abrir la app, sin tocar ningún botón — se
  implementó así (`AtlasWindow.__init__` llama a
  `_on_wake_word_toggle_clicked()` al final), aunque contradice el
  principio general de "apagado por defecto" que se sigue en todo lo demás
  (cámara para gestos, voz Push-to-Talk). Es una decisión consciente del
  usuario sobre su propia app, no una relajación general del principio.
- **Falsos positivos con conversaciones de fondo**: `contains_wake_word`
  originalmente buscaba "atlas" en cualquier parte del texto transcrito.
  Se acotó a que "atlas" debe aparecer entre las primeras dos palabras
  (como cuando alguien te llama por tu nombre al empezar a hablarte) —
  reduce (no elimina del todo) que una charla de fondo que mencione "atlas"
  de pasada dispare el asistente.
- Sin motor de wake-word dedicado (Porcupine pide cuenta/licencia,
  openWakeWord no trae modelo en español para "Atlas"): se reutiliza
  Whisper, con el costo conocido de más latencia (~1-3s) que un motor
  dedicado.
- Validado en vivo, end-to-end, dos veces seguidas: "Atlas, ¿qué hora es?"
  → respuesta correcta por texto y voz; "Atlas, gracias" → "¡De nada!".

## Fase 6: Automation Engine

- Reutiliza el Event Bus de Fase 2 tal como estaba planeado desde
  entonces: `AUTOMATION_TRIGGERED`/`AUTOMATION_COMPLETED`/
  `DEVICE_STATE_CHANGED`/`NOTIFICATION_CREATED` ya existían como tipos de
  evento sin que nadie los publicara — Fase 6 los conecta de verdad.
- **Regla de seguridad que no depende de quién dispara la rutina**: se
  agregó `Tool.resolve_risk_level()` en Fase 5 pensando solo en
  `set_device_state`; acá se reutiliza en `execute_routine()`
  (`app/automation/service.py`) para decidir, acción por acción, si se
  ejecuta (`READ_ONLY`/`LOW_RISK`) o se salta. No hay una ruta separada
  para "el usuario está presente y puede confirmar" — una rutina disparada
  por voz en el momento sigue el mismo camino que una disparada por
  horario a las 3 AM sin nadie mirando. Cuando se salta una acción, se
  publica `NOTIFICATION_CREATED` con el motivo — la entrega real de esa
  notificación (push al móvil) es Fase 7; acá solo se genera el evento.
- Dos motores de trigger separados, porque necesitan mecanismos distintos:
  - `app/automation/scheduler.py`: una tarea `asyncio` (arrancada/parada en
    el `lifespan` de `app/main.py`) que revisa triggers `SCHEDULE` cada 30s
    comparando contra la hora actual, con protección para no disparar dos
    veces dentro del mismo minuto.
  - `app/automation/engine.py`: triggers `DEVICE_STATE` se resuelven
    suscribiéndose a `DEVICE_STATE_CHANGED` en el Event Bus — para que esto
    funcione, `SetDeviceStateTool` y `ControlRoomTool` (Fase 5) ahora
    reciben `EventBus` inyectado y publican ese evento tras cada cambio
    real. Incluye una protección básica contra recursión (un `set` de
    rutinas en ejecución) para el caso obvio de que una rutina dispare su
    propio trigger.
- `run_routine` (tool) resuelve un problema de orden de construcción: para
  poder buscar otras tools dentro de sí misma necesita una referencia al
  propio `ToolRegistry` que la contiene. Se resuelve construyéndola al
  final de `build_default_registry()`, pasándole el objeto `registry` que
  ya existe (aunque siga llenándose) en ese punto.
- Validado en vivo con Claude real + `MockSmartHomeProvider`: "ejecuta mi
  rutina de dormir" apagó exactamente los dispositivos de la rutina; una
  rutina con una acción `CRITICAL` (desbloquear una cerradura) la saltó
  automáticamente sin tocarla, dejando constancia en `skipped`. El trigger
  de horario también se confirmó en vivo: se creó una rutina "Prueba
  Horario" con `{"time": "14:09"}` mientras la luz estaba encendida, y el
  log del servidor muestra que a las 14:09:11 —sin ninguna request manual
  de por medio— se disparó sola: `AUTOMATION_TRIGGERED` →
  `DEVICE_STATE_CHANGED (light.sala → off)` → `AUTOMATION_COMPLETED`.

## Fase 7: app móvil (PWA) + autenticación

- **El JWT_SECRET reservado desde la Fase 1 finalmente se usa.** Sistema de
  un solo usuario (no hay tabla de usuarios): `ATLAS_PASSWORD` en `.env`
  se compara en texto plano contra lo que manda `/api/v1/auth/login`
  (`app/security/auth.py`) — razonable para credenciales de un solo usuario
  local, mismo criterio que `ANTHROPIC_API_KEY`/`SMART_HOME_TOKEN`, aunque
  con hashing sería más robusto si esto creciera a más de un usuario.
- **Auth aplicado a nivel de router, no endpoint por endpoint**
  (`app/api/v1/router.py`, `dependencies=[Depends(get_current_user)]` al
  incluir cada router) — evita el riesgo de olvidarse de proteger algún
  endpoint nuevo a mano. `system.router` es la excepción: mezcla
  `/health` (público, chequeo de vida) con `/status` (protegido), así que
  ahí se aplicó `Depends` directo en el segundo endpoint.
- **El cliente de escritorio dejó de ser anónimo.** Antes de esta fase
  hablaba con el backend sin ningún token; se actualizó
  `desktop/atlas_desktop/api_client.py` (login al arrancar, header en cada
  request) y `main.py` (diálogo de contraseña si `ATLAS_PASSWORD` no está
  en `desktop/.env`) en el mismo cambio — no después, para no dejar el
  escritorio roto mientras tanto.
- **Notificaciones: "en la app", no push del sistema operativo.** Push real
  (Web Push/VAPID) necesita HTTPS, que no está configurado para acceso por
  red local. Se optó por persistir cada `NOTIFICATION_CREATED` del Event
  Bus (`app/notifications/`) y que el cliente las liste al abrir/refrescar
  — decisión explícita, no una implementación a medias de push real.
- **Cliente móvil sin Flutter, sin Node/npm**: HTML/CSS/JS vanilla
  (`mobile/`), servido por un `http.server` mínimo (`mobile/serve.py`) que
  escucha en `0.0.0.0` para que el celular entre por la IP local de la PC.
  Mismo criterio que evitar C#/.NET en el escritorio: menos piezas móviles,
  todo corre con solo Python.
- **Bug real encontrado y corregido: CORS.** Al probar el login desde la
  PWA (puerto 5173) contra la API (puerto 8000), el navegador lo bloqueó
  con "Failed to fetch" — orígenes distintos, sin `CORSMiddleware`
  configurado. Se agregó en `app/main.py` con `allow_origins=["*"]`:
  aceptable acá porque la autenticación es por Bearer token, no por
  cookies de sesión (un origen abierto no expone nada que el token no
  controle ya).
- **Bug real (mismo patrón que en `desktop/run.py` y el wake word):**
  `mobile/serve.py` también crasheaba con `UnicodeEncodeError` al imprimir
  una flecha (→) en la consola cp1252 de Windows. Mismo fix: reconfigurar
  `stdout`/`stderr` a UTF-8 al arrancar.
- **Limitación conocida, no a medias**: `getUserMedia` (micrófono del
  navegador) exige un "contexto seguro" — HTTPS o `localhost`. Sin HTTPS
  para la red local, la voz funciona desde la PC (`127.0.0.1`) pero podría
  fallar desde el celular por IP (`192.168.x.x`). Pendiente de confirmar
  con el usuario en persona — ver `docs/pending-manual-tests.md`.
- **Alcance de "remoto" limitado a la misma red WiFi** — no hay dominio ni
  HTTPS público; controlar la casa desde fuera de casa queda fuera de esta
  fase, documentado explícitamente en vez de simulado a medias.
- Validado en vivo: login rechaza contraseña incorrecta y acepta la
  correcta; `/chat` sin token devuelve 401; el cliente de escritorio se
  loguea solo al arrancar; la PWA (probada desde la propia PC) loguea,
  manda mensajes de chat con respuesta real de Claude, y lista dispositivos
  reales desde el navegador.

## Fase 8: Visión

- **Sin `VisionProvider` "de verdad" aparte de Claude.** Claude ya es
  multimodal — `AnthropicVisionProvider` (`app/vision/anthropic_provider.py`)
  simplemente manda la imagen como bloque `image` en el mismo formato de
  mensajes que ya usa `AnthropicProvider` para chat. No hay un servicio de
  visión externo que mantener.
- **Sin motor de OCR aparte** (Tesseract, etc.): se le pide a Claude en el
  prompt que incluya cualquier texto legible como parte de la descripción.
  Validado en vivo: una imagen generada con el texto "ATLAS TEST 2026" se
  analizó correctamente vía `POST /api/v1/vision/analyze` y el texto volvió
  exacto en la respuesta — confirma que la decisión de no agregar Tesseract
  fue correcta para este caso de uso, no una simplificación a medias.
- **Captura de pantalla vive en el backend, no en `desktop/`** — a
  diferencia de la cámara/micrófono (Fase 3/gestos), que si son recursos
  del cliente. La pantalla que ATLAS debe "mirar" es la de la PC donde
  corre el backend, mismo criterio que `get_system_info`/`open_application`
  (tools que ya operan sobre esa misma máquina). Implementado con `Pillow`
  (`ImageGrab.grab()`), sin dependencia nueva de peso.
- **`analyze_screenshot` es `HIGH_RISK`**, igual que "acceder a una cámara"
  en la sección 5 — una captura de pantalla puede exponer información tan
  sensible como una cámara (contraseñas visibles, chats privados). Pide
  confirmación siempre; una rutina que la incluya la salta automáticamente
  sin necesitar código nuevo — ya la protegía `execute_routine` de la
  Fase 6 en base al `resolve_risk_level` de la tool, no a una lista
  hardcodeada de nombres de tools "peligrosas".
- Validado en vivo con Claude real: pedir "mira mi pantalla y decime qué
  hay" pidió confirmación (`HIGH_RISK`), y al aprobarla describió con
  precisión la pantalla real en ese momento — incluido texto de una
  terminal (VS Code, estructura del proyecto, output de una sesión previa
  de wake word).

## Fase 9: Dashboard / interfaz futurista (última fase)

- **Tercer cliente, no una reescritura de los otros dos.** `desktop/`
  (funcional, control profundo de Windows) y `mobile/` (táctil, pantalla
  angosta) siguen como están — `dashboard/` es una capa de presentación
  nueva para pantalla ancha de PC, mismo criterio HTML/CSS/JS vanilla que
  `mobile/` (sin Node/npm, sin build). Cero lógica de negocio nueva: todo
  el layout habla con la misma API ya construida en las 8 fases previas.
- **Ningún widget con datos falsos.** El mockup original del usuario tenía
  una tarjeta de "recordatorios" — no se incluyó, porque ATLAS no tiene un
  sistema de recordatorios/calendario real. Cada tarjeta del dashboard
  corresponde a un endpoint real ya probado en fases anteriores
  (`/system/status`, `/devices`, `/automations`, `/notifications`,
  `/memory`), más uno nuevo:
- **`GET /api/v1/system/activity`** (`app/security/audit.py::list_recent`):
  `AuditLog` existe desde la Fase 1, pero hasta ahora ningún cliente podía
  consultarlo — vivía solo en la base de datos. Es el primer endpoint que
  expone esa tabla, cerrando el círculo de "actividad de ATLAS" que pedía
  la sección 20 del prompt maestro.
- **Visualizador de audio real, no decorativo**: `Web Audio API`
  (`AnalyserNode`) conectado directo al `MediaStream` del micrófono
  mientras se graba, y al elemento `<audio>` de la respuesta mientras
  ATLAS habla — las barras que se ven representan el audio real en cada
  momento, no una animación con datos inventados.
- **Identidad visual propia**: paleta oscura + acento cian (`#4fc3f7`),
  reusada literalmente de `mobile/styles.css` para consistencia de marca
  entre los tres clientes — deliberadamente lejos del rojo/dorado de Iron
  Man, cumpliendo la restricción explícita del prompt maestro (sección 20:
  "NO copies diseños protegidos de Marvel/Iron Man").
- Validado en vivo por el usuario: login, chat con respuesta real,
  navegación entre las 7 secciones (Inicio, Chat, Dispositivos, Rutinas,
  Notificaciones, Memoria, Actividad), y anillos de CPU/RAM/Disco con
  valores reales.

**Nota honesta sobre esta fase**: este documento y el README describían la
Fase 9 como terminada, pero la carpeta `dashboard/` estaba vacía — el
backend (endpoint `/system/activity`, tests) sí se había construido, el
cliente (HTML/CSS/JS) nunca se llegó a escribir. Se detectó recién al
retomar el proyecto para otra cosa (el usuario pidió abrir el dashboard) y
se construyó en el momento, siguiendo exactamente lo que estos documentos
ya describían. Queda como recordatorio de verificar con `ls`/`Glob` lo que
el código dice que existe, no solo lo que la documentación afirma.

## Control por gestos: celular controla el mouse de la PC (fuera del prompt maestro, a pedido)

- **Por qué cámara del celular y no la webcam de la PC**: el diseño
  original parqueado (`docs/future-gesture-control.md`, ahora superado)
  usaba la webcam de la PC + MediaPipe en Python, con un riesgo técnico sin
  resolver (MediaPipe podía no tener wheel para Python 3.13). Usar la
  cámara del celular evita ese riesgo por completo: MediaPipe Tasks Vision
  corre en el navegador (JS/WASM, `@mediapipe/tasks-vision` vía CDN — único
  recurso externo cargado en todo el proyecto), sin instalar nada nuevo en
  el backend salvo `pyautogui` (liviana, sin dependencias de visión).
- **División de trabajo**: el celular detecta la mano y manda solo
  coordenadas normalizadas por WebSocket (`/api/v1/gestures/stream`) —
  nunca video. El backend (que corre en la misma PC que se quiere
  controlar, mismo criterio que `analyze_screenshot` en Fase 8) mueve el
  mouse real con `pyautogui`. Autenticación: el JWT no puede ir en headers
  de un WebSocket del navegador, así que se manda como primer mensaje tras
  conectar y se valida con `is_token_valid()` (variante de
  `get_current_user()` que no depende de HTTPException, ver
  `app/security/auth.py`).
- **Sin Permission Manager**: igual que el mouse/teclado físicos, es
  entrada continua de bajo nivel — no pasa por el Orchestrator ni por
  tool calling, mismo criterio ya usado para el mouse en el diseño
  original.
- **Dos manos, un trabajo cada una**: la primera versión intentó que una
  sola mano hiciera cursor + clic + scroll con distintas formas de los
  dedos, y en la práctica los gestos se confundían entre sí (un pellizco
  movía el cursor porque el cursor seguía la *punta* del índice, que se
  desplaza hacia el pulgar al pellizcar). Solución: **mano derecha =
  cursor** (sigue el nudillo del índice, landmark 5 — casi no se mueve al
  pellizcar, a diferencia de la punta) **+ pellizco = clic**; **mano
  izquierda = puño cerrado, movido arriba/abajo = scroll**. `numHands: 2`
  en el `HandLandmarker`, separadas por `handedness.categoryName` de
  MediaPipe. Requiere que el celular esté apoyado/fijo (no sostenido en la
  mano) para que la cámara vea ambas manos libres — si se sostiene con una
  mano, solo queda una mano libre para gesticular.
- **Umbrales relativos al tamaño de la mano, no distancias fijas**: la
  primera versión del pellizco usaba una distancia normalizada fija
  (`0.06`) entre pulgar e índice, que resultaba demasiado estricta cuando
  la mano estaba lejos de la cámara (todo se achica junto con la
  distancia). Se cambió a una fracción del tamaño de la mano en cámara
  (`dist(muñeca, nudillo_medio) * 0.55`) — funciona igual sin importar la
  distancia a la cámara. Mismo criterio para "puño cerrado" (dedo doblado
  = la punta queda más cerca de la muñeca que el nudillo, en vez de una
  distancia fija).
- **Detección de puño necesita umbrales de confianza más bajos**: un puño
  cerrado es más difícil de reconocer como "mano" para el detector de
  MediaPipe que una mano abierta apuntando (menos dedos articulados
  visibles). `minHandDetectionConfidence`/`minHandPresenceConfidence`/
  `minTrackingConfidence` bajados de 0.5 (default) a 0.3.
- **Requiere HTTPS**: `getUserMedia` (cámara) exige un "contexto seguro" —
  HTTPS o `localhost`. El celular, por IP de LAN, no es `localhost`, así
  que hace falta certificado. Ver `scripts/generate_dev_cert.py` y la
  sección de HTTPS en el README.
- **Bug encontrado durante esta prueba, no relacionado a gestos**:
  `backend/run.py` estaba atado a `host="127.0.0.1"` desde la Fase 1 —
  ningún dispositivo externo (celular incluido) pudo alcanzar el backend
  nunca, solo no se había notado porque hasta ahora nadie había probado
  `mobile/`/`dashboard/` desde fuera de la propia PC. Corregido a
  `host="0.0.0.0"`.
- **Bug encontrado después, en el cliente de escritorio**: al generar el
  certificado y pasar el backend a HTTPS-only, el cliente de escritorio
  (`desktop/`) seguía apuntando a `http://127.0.0.1:8000` por default —
  `requests` fallaba con un error de conexión al loguearse, que caía al
  diálogo manual de contraseña; ese diálogo, corriendo sin sesión
  interactiva visible, devolvía `None` en silencio y el proceso salía con
  código 0 sin ningún log ni traceback. Parecía "el wake word no
  funciona" cuando en realidad la ventana ni llegaba a abrirse. Corregido
  en `desktop/atlas_desktop/config.py`: detecta el esquema (`http`/`https`)
  según si existe `certs/dev-cert.pem`, y valida la conexión contra ese
  certificado (`ATLAS_CA_CERT`) en vez de desactivar la verificación TLS.
- **Service Worker de la PWA cacheaba `app.js` viejo**: cada cambio al
  código de gestos requirió subir `CACHE_NAME` en `mobile/sw.js` para que
  el celular dejara de servir la versión vieja desde caché — un cierre y
  reapertura completos de la pestaña, no solo un refresh, para que el
  nuevo Service Worker tome control.
