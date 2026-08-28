# ATLAS

Asistente personal de inteligencia — un sistema modular tipo JARVIS, construido
desde cero, original, no un chatbot.

**Fase 29 (Migraciones formales con Alembic + streaming de chat + varias mejoras de robustez):**
- **Alembic reemplaza `Base.metadata.create_all()` + el parche manual de
  columnas tardías** (`app/core/database.py`). Ya llevaba dos parches de ese
  tipo (`reminders.notified`, `memory_entries.embedding`) — cada uno una
  forma más de romper una base existente si alguien se olvidaba de
  escribirlo. `init_db()` ahora corre `alembic upgrade head`, que crea la
  base desde cero *o* la evoluciona si ya existe, con la misma operación.
  Caso especial: una base creada antes de este cambio (cualquier `atlas.db`
  de una instalación existente) ya tiene todas las tablas pero no la de
  control de Alembic — se detecta y se marca (`stamp head`) en vez de
  intentar recrearlas. Migración baseline en `migrations/versions/`.
  - Bug real encontrado al probarlo: con SQLite `:memory:` (la base que usan
    los tests), Alembic abría su propia conexión nueva para migrar — y una
    base en memoria vive solo en la conexión que la creó, así que el motor
    real de la app se quedaba sin tablas. Se resolvió pasándole el `Engine`
    real de la app a Alembic (`config.attributes["connection"]`) en vez de
    dejar que arme uno nuevo a partir de la URL.
  - 4 tests nuevos (`tests/test_database.py`): base nueva, dos corridas
    seguidas (idempotencia), base pre-Alembic (stamp), base ya migrada
    (upgrade).
- **Streaming de respuestas** (`POST /api/v1/chat/stream`, Server-Sent
  Events): el dashboard ya no espera la respuesta completa — el texto
  aparece a medida que Claude lo genera, y un evento `tool_call` avisa
  "usando `<tool>`..." mientras corre una herramienta (clima, búsqueda web,
  etc.), en vez del silencio de antes. `AIProvider.chat_stream()` nuevo
  (`app/ai/base.py`), con streaming real en `AnthropicProvider` (vía
  `client.messages.stream()`) y fallback automático a la respuesta completa
  para `MockProvider`. El Orchestrator ganó `handle_message_stream`,
  compartiendo con la versión síncrona los mismos helpers de evaluación y
  ejecución de tools (`_evaluate_tool_calls`/`_execute_resolved_calls`) para
  que ambas versiones no puedan divergir en qué se ejecuta solo y qué pide
  confirmación.
  - Bug real encontrado al probarlo: una sesión de DB inyectada por
    `Depends()` se cierra apenas el endpoint retorna el `StreamingResponse`,
    antes de que el generador la termine de usar — rompía con "no such
    table" recién al testear. Se resolvió resolviendo `get_db_session` a
    mano desde `request.app.dependency_overrides` (mismo mecanismo que usa
    FastAPI puertas adentro), para no perder el override que usan los tests.
- **El Orchestrator resuelve todos los `tool_calls` de un turno**, no solo
  el primero — antes, si el modelo pedía varias tools de una, el resto del
  lote se perdía sin ejecutarse. Si alguna del lote necesita confirmación,
  no se ejecuta ninguna (todo o nada por turno, mismo criterio que ya regía
  para un solo call). Requirió que `AnthropicProvider` agrupe varios
  `tool_result` en un único turno "user" — Anthropic rechaza turnos "user"
  consecutivos.
- **Historial de conversación acotado por tokens estimados**, no por
  cantidad de mensajes — 20 mensajes cortos no pesan lo mismo que 20 largos.
- **Revocación de JWT** (`POST /auth/logout`): antes cerrar sesión solo
  borraba el token del `localStorage`; uno filtrado seguía sirviendo hasta
  que expirara solo (24h por defecto). Estado en memoria de proceso, mismo
  criterio que `login_rate_limiter`/`permission_manager`.
- **Rate limiting en `/chat`** (30 req/min por IP) — antes solo
  `/auth/login` lo tenía.
- Los errores del `AIProvider` ya no filtran el detalle de la excepción al
  usuario (solo al log) — podía traer texto interno del proveedor sin
  aportarle nada a quien lo lee.
- **Miniaturas reales para Shazam** (`/api/v1/music/identify`): se pedía
  `return=spotify` a AudD pero solo se usaba su `song_link` (un smart-link
  sin imagen asociada) — se aprovecha la metadata real que ya venía en la
  respuesta. Orden de fuentes: Spotify → Apple Music → YouTube (búsqueda por
  "artista + título", solo si las dos anteriores no tuvieron match) → texto
  plano si ninguna la tiene. 6 tests nuevos.
- CORS quedó **sin cambios a propósito**: se evaluó restringirlo, pero el
  auth es por header Bearer (no cookies) — un origen ajeno no tiene el token
  para explotar el wildcard, y restringir por origen fijo habría roto el
  acceso por IP de LAN (que cambia según la red). La justificación original
  del código sigue siendo correcta.
- **Primer smoke test E2E** (`dashboard/tests_e2e/`, Playwright): hasta acá
  los ~300 tests de `backend/tests/` prueban la API a fondo, pero ninguno
  ejecuta el JavaScript del dashboard en un navegador real. Backend y
  servidor estático se levantan dentro del propio proceso de test (uvicorn
  y `http.server` en threads, puerto dinámico) en vez de como subprocesos —
  sin eso, sin querer, se termina reproduciendo el mismo bug de sockets
  huérfanos de Windows que ya documentó este README (Fase 16). Cubre login,
  el chat de punta a punta contra `/chat/stream` (primera vez que el
  streaming se prueba en un navegador real, no solo vía `TestClient`/`curl`),
  la vista de Dispositivos y logout. Ver `dashboard/tests_e2e/README.md`
  para cómo correrlo — no está en el CI todavía (`.github/workflows/`), a
  propósito: agregar un browser real ahí es una decisión aparte.
- 39 tests nuevos en total (299 → ~303 en `backend/tests/`, + 5 en
  `dashboard/tests_e2e/`).

**Fase 20 (Búsqueda semántica de memoria):**
- `app/embeddings/`: `EmbeddingProvider` desacoplado, mismo patrón que
  `AIProvider`/`VoiceProvider`/`SmartHomeProvider`. `FastEmbedProvider`
  (real, `EMBEDDING_PROVIDER=fastembed`) usa el modelo local
  `all-MiniLM-L6-v2` vía `fastembed` (ONNX, ~90MB, gratis, sin API key, sin
  mandar nada a internet una vez descargado) en vez de
  `sentence-transformers`, que arrastra PyTorch completo solo para correr
  el mismo tipo de modelo chico. `MockEmbeddingProvider` (default,
  determinístico por hash de palabras) evita que tests/desarrollo rápido
  necesiten el modelo instalado.
- `MemoryEntry` gana una columna `embedding` (JSON, nullable) — nullable a
  propósito: las memorias creadas antes de este cambio quedan sin vector
  hasta correr `scripts/backfill_memory_embeddings.py`, y mientras tanto
  siguen siendo encontrables por el fallback de texto.
- `search_memories()` pasa a ser híbrida: LIKE (determinístico, se
  prioriza) + similitud de coseno contra el embedding de la consulta,
  calculada en Python puro sobre las entradas en SQLite — sin sqlite-vec ni
  vector DB aparte, coherente con el volumen real de una memoria personal
  (cientos de entradas, no millones) y con el resto del proyecto
  ("SQLite en vez de Postgres, sin Docker"). Si el volumen crece, el punto
  de upgrade documentado es sqlite-vec.
- Si el `EmbeddingProvider` falla al guardar una memoria, no rompe
  `create_memory`: la memoria se guarda igual, sin vector, y sigue siendo
  encontrable por texto.

**Fase 21 (Google Calendar):**
- `app/integrations/google_calendar.py`: OAuth2 "instalada" (flujo
  loopback) vía `requests` puro, sin el SDK oficial
  (`google-api-python-client`) — mismo criterio que
  `home_assistant_provider.py`: llamadas REST simples no justifican una
  dependencia pesada. `GoogleCalendarClient` cachea el access_token en
  memoria del proceso (dura ~1h) y lo renueva con el refresh_token, que no
  expira.
- Dos tools nuevas (`app/tools/calendar/`): `list_calendar_events`
  (READ_ONLY) y `create_calendar_event` (LOW_RISK, mismo criterio que
  `create_reminder`: escribe en un servicio externo real pero no tiene
  consecuencias irreversibles en el mundo físico, así que no exige
  confirmación). Distinto de un recordatorio a propósito: un evento de
  calendario queda visible en Google Calendar y cualquier app que lo
  sincronice; un recordatorio solo vive en ATLAS.
- `scripts/google_calendar_setup.py`: hace el paso que no se puede
  automatizar del todo — la pantalla de consentimiento del navegador.
  Levanta un servidor local temporal en `localhost:8765` para recibir el
  código de autorización del redirect, lo cambia por un `refresh_token` y
  dice qué pegar en `.env`. Mismo espíritu que `scripts/tuya_setup.py`:
  resolver la parte más molesta de configurar la integración.
- Sin `GOOGLE_CLIENT_ID`/`GOOGLE_CLIENT_SECRET`/`GOOGLE_REFRESH_TOKEN`
  configurados, las tools devuelven un error explicando qué falta (mismo
  criterio que YouTube/Spotify/AudD) en vez de romper el resto de ATLAS.
- 9 tests nuevos, mockeando `requests` — no pegan a la API real de Google.

**Fase 22 (Push notifications reales):**
- `app/notifications/`: nueva tabla `PushSubscription` (una fila por
  navegador/dispositivo suscripto — el mismo usuario puede tener el celular
  y el dashboard suscriptos a la vez). `send_web_push()` se cuelga del mismo
  subscriber de `NOTIFICATION_CREATED` que ya persistía en `Notification`
  (Fase 7): la notificación "en la app" no desaparece, Web Push se suma
  para avisar aunque la app esté cerrada.
- Web Push real vía `pywebpush` + claves VAPID (RFC 8292) — no depende de
  ninguna cuenta externa, a diferencia de Google Calendar/Tuya: el par de
  claves se genera una sola vez con `scripts/generate_vapid_keys.py`
  (EC P-256 vía `cryptography`, ya una dependencia del proyecto).
- Endpoints nuevos: `GET /notifications/push/public-key`,
  `POST`/`DELETE /notifications/push/subscribe`.
- `shared/push.js` + `shared/push-sw.js` (compartidos entre `mobile/` y
  `dashboard/`, mismo criterio que `wake-word.js`): manejan el permiso del
  navegador, la suscripción (`PushManager.subscribe`) y la notificación
  visual (`showNotification` dentro del service worker). `dashboard/`
  no tenía service worker — se agregó `dashboard/sw.js` solo para esto, sin
  cachear el shell (a propósito: el dashboard no es una PWA instalable).
- Suscripción muerta (navegador desinstalado, datos borrados): el servicio
  push devuelve 404/410, y `send_web_push()` borra esa fila en vez de
  seguir intentando mandarle para siempre. Cualquier otro error (falla
  transitoria del servicio push) no borra la suscripción.
- Ya no depende de exponer la red local sin HTTPS: la Fase 16 dejó
  `certs/dev-cert.pem` como requisito para cámara/micrófono, y ese mismo
  contexto seguro es el que ahora también habilita `PushManager.subscribe()`.
- 11 tests nuevos, mockeando `pywebpush.webpush` — no le pegan a ningún
  servicio push real.

**Fase 23 (Gmail):**
- `app/integrations/gmail.py`: mismo criterio que `google_calendar.py`
  (`requests` puro, sin SDK) y **la misma cuenta/credenciales** —
  `GOOGLE_CLIENT_ID`/`GOOGLE_CLIENT_SECRET`/`GOOGLE_REFRESH_TOKEN` ya
  configurados para Calendar sirven para Gmail también, siempre que el
  refresh_token incluya el scope nuevo (ver abajo).
- Dos tools (`app/tools/gmail/`): `list_unread_emails` (READ_ONLY) y
  `send_email` (**MEDIUM_RISK**, a diferencia de `create_calendar_event`:
  mandar un correo es una acción hacia un tercero e irreversible, no algo
  que solo queda en herramientas propias del usuario — mismo nivel que
  `close_application`, pide confirmación antes de ejecutarse).
- Scopes mínimos a propósito: `gmail.readonly` + `gmail.send`, no
  `gmail.modify`/`gmail.full` — las tools no necesitan borrar ni archivar
  correo, y pedir de menos es más fácil de justificar en la pantalla de
  consentimiento.
- `scripts/google_calendar_setup.py` ahora pide los scopes de Calendar y
  Gmail **en la misma pasada**: un solo refresh_token cubre ambas
  integraciones. Si el refresh_token ya existía de la Fase 21 (Calendar
  solo), hay que volver a correr el script — el token viejo no tiene el
  scope de Gmail y las tools fallan con `GmailNotConfigured` hasta
  reemplazarlo.
- 9 tests nuevos, mockeando `requests`.

**Fase 24 (Mapas/tráfico):**
- `app/integrations/maps.py`: Nominatim (geocoding) + OSRM (ruteo) —
  OpenStreetMap, gratis y **sin API key ni cuenta**, mismo criterio que
  Open-Meteo (clima) y DuckDuckGo (búsqueda web). Se prefirió explícitamente
  a Google Maps Distance Matrix, que exige habilitar facturación en Google
  Cloud aunque el uso caiga dentro del crédito gratis.
- Tool `get_travel_time` (READ_ONLY): distancia y tiempo estimado en auto
  entre dos lugares.
- **Limitación real, no escondida**: los servidores públicos de OSRM no dan
  tráfico en tiempo real, solo velocidad promedio por tipo de vía — la
  respuesta aclara "estimado, sin tráfico en tiempo real" en vez de fingir
  precisión que no tiene (mismo criterio que la Fase 11 con la temperatura
  de CPU: sin el dato real, no se inventa uno).
- Verificado en vivo contra los servidores reales (no mockeados): Santo
  Domingo → Santiago, 155.2 km, ~122 min.
- 8 tests nuevos, mockeando `requests`.

**Fase 25 (Rate limiting de login):**
- `app/security/rate_limit.py`: `LoginRateLimiter`, mismo patrón que
  `PermissionManager` (estado en memoria de proceso — para un solo usuario
  en un solo proceso alcanza, escalar a múltiples workers pediría Redis).
  Bloquea por IP tras `LOGIN_MAX_ATTEMPTS` fallos seguidos (5 por defecto),
  por `LOGIN_LOCKOUT_SECONDS` (900 = 15 min).
- Hueco real que cerraba: desde que existen clientes remotos (móvil,
  dashboard por red), cualquiera con acceso a la WiFi podía probar
  `ATLAS_PASSWORD` sin límite — `/auth/login` no tenía ningún freno. No es
  2FA ni reemplaza una contraseña fuerte, pero convierte un ataque de
  fuerza bruta práctico en uno que tardaría años.
- Un login correcto limpia el historial de fallos de esa IP — no tiene
  sentido seguir penalizando al dueño real de la cuenta por intentos viejos.
  `429` con header `Retry-After` mientras está bloqueada.
- 11 tests nuevos. Trampa encontrada al escribirlos: el rate limiter es un
  singleton de proceso — sin resetear su estado entre tests, un test que
  agota los intentos dejaba la IP de prueba bloqueada 15 minutos reales
  para *todos* los tests que corrieran después (`auth_headers`, que usan
  casi todos, hace login). Se resolvió con un fixture `autouse` en
  `conftest.py` que lo limpia antes y después de cada test.

**Fase 26 (Backups automáticos de la base de datos):**
- `app/core/backup.py`: usa `sqlite3.Connection.backup()` (API online de
  SQLite) en vez de copiar el archivo a mano — una copia cruda mientras hay
  escrituras en curso puede capturar un estado a medio escribir y quedar
  corrupta; el backup online es seguro con la base en uso.
- `BackupScheduler`: mismo patrón que `ReminderScheduler`/
  `AutomationScheduler` (tarea en background del propio proceso). Un
  backup al arrancar + uno cada `BACKUP_INTERVAL_HOURS` (24 por defecto)
  mientras el proceso sigue corriendo — el arranque es necesario porque
  ATLAS no es un servidor 24/7, es un asistente de escritorio que se
  prende y apaga con el uso.
- Rotación simple: se conservan los `BACKUP_KEEP_COUNT` más recientes (7
  por defecto), se borran los más viejos.
- Solo aplica a SQLite (`DATABASE_URL` por defecto). Si el proyecto migra a
  PostgreSQL, se avisa por log en vez de fallar en silencio o fingir que
  hizo un backup que no hizo — mismo criterio que la temperatura de CPU en
  la Fase 11.
- 4 tests nuevos, con una base SQLite real en un directorio temporal (no
  tocan `backend/atlas.db`). Bug encontrado escribiéndolos: el nombre del
  archivo de backup solo tenía resolución de segundo — dos backups en el
  mismo segundo se pisaban entre sí. Se agregaron microsegundos al timestamp.

**Fase 27 (CI):**
- `.github/workflows/backend-tests.yml`: corre los 263+ tests del backend
  en cada push/PR que toque `backend/`. No existía ningún CI — con esa
  cantidad de tests ya escritos, la parte más barata de aprovecharlos
  (correrlos solos) era justo la que faltaba.
- Runner `windows-latest`, no Ubuntu: el proyecto importa `pyautogui`
  (control de mouse por gestos) a nivel de módulo, sin diferir — eso rompe
  la importación completa de la app en un runner Linux sin servidor X.
  Coincide además con la plataforma real del proyecto (WMI, voces SAPI).
- Sin secretos ni credenciales: `AI_PROVIDER`/`STT_PROVIDER`/etc. ya caen en
  `mock` por defecto y `conftest.py` fuerza vacías las credenciales de
  integraciones externas — el único valor que hace falta fijar es
  `ATLAS_PASSWORD`, hardcodeado como `test-password` en el workflow (no es
  secreto real, es la misma contraseña de prueba que ya usa `conftest.py`).

**Fase 28 (Límite de gasto en la API de Anthropic):**
- `app/core/usage.py`: tabla `ApiUsage` (una fila por llamada real a Claude,
  con tokens y costo estimado) + `check_budget()`, que el Orchestrator
  consulta **antes de cada llamada** al `AIProvider` — no solo al principio
  del turno: un loop de tool calling insistente (`MAX_TOOL_ITERATIONS`)
  también gasta, y el freno tiene que poder cortarlo a mitad de turno.
- El costo es una **estimación por tabla de precios** (`opus`/`sonnet`/
  `haiku`, USD por millón de tokens), no la factura real de Anthropic —
  documentado como tal en el propio código, mismo criterio que la
  temperatura de CPU en la Fase 11: mejor una estimación aproximada y
  etiquetada que fingir precisión que no se tiene.
- `ANTHROPIC_DAILY_BUDGET_USD` (5 por defecto) y `ANTHROPIC_MONTHLY_BUDGET_USD`
  (0 = sin tope) en `.env`. Al superarse, el Orchestrator devuelve un
  mensaje explicando el límite en vez de llamar a la API — no rompe con un
  500, se comporta como una respuesta más.
- `MockProvider` no cuenta: `AIResponse.input_tokens`/`output_tokens` quedan
  en 0 salvo que el proveedor real (`AnthropicProvider`, vía
  `response.usage`) los complete — nada que medir sin pegarle a la API
  real, mismo espíritu que el resto de los mocks del proyecto.
- 9 tests nuevos, incluida una integración completa con el Orchestrator
  (un `AIProvider` de prueba que cuenta cuántas veces se lo llamó, para
  verificar que el límite corta la llamada *antes* de que ocurra, no
  después).

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

**Wake word "Ali" (agregado sobre la Fase 4, cliente de escritorio):**
- Se llamaba "Atlas"; se probó "Vision" pero Whisper (forzado a español)
  alucinaba palabras random tratando de encajar su pronunciación inglesa
  en fonética española. "Ali" es corta y sin sonidos ambiguos, transcribe
  mucho más consistente.
- Escucha continua activada automáticamente al abrir el cliente (pedido
  explícito del usuario — no queda apagada por defecto como el resto de las
  capturas de cámara/audio del proyecto). Botón "👂 Escucha" para
  apagarla/prenderla manualmente.
- Reutiliza Whisper (sin motor de wake-word dedicado): buffer de audio
  deslizante + filtro de energía + `/api/v1/voice/transcribe` con idioma
  forzado a español. Solo reacciona si "Ali" aparece entre las primeras
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

**Fase 10 (Integraciones externas — Wikipedia, clima, YouTube, Spotify):**
- 4 tools nuevas, mismo patrón que el resto (`app/tools/`, JSON Schema +
  `RiskLevel.READ_ONLY` — solo leen, nunca actúan): `search_wikipedia`,
  `get_weather`, `search_youtube`, `search_spotify`.
- Wikipedia (`app/integrations/wikipedia.py`) y clima
  (`app/integrations/weather.py`, vía Open-Meteo) no necesitan API key,
  andan siempre. YouTube y Spotify sí — ver `.env.example` para cómo
  conseguirlas gratis; si falta la key, la tool devuelve un error
  explicativo en vez de romper el resto de ATLAS.
- Spotify usa Client Credentials Flow (solo búsqueda pública, sin login de
  usuario) — no controla reproducción; eso requeriría OAuth de tu cuenta +
  Spotify Premium + un dispositivo activo, fuera de alcance de esta fase.
- **Spotify — bloqueado por falta de Premium**: código completo y probado
  (`search_spotify`, credenciales ya cargadas en `.env`), pero Spotify
  devuelve `403 Active premium subscription required for the owner of the
  app` — política nueva (2025): incluso Client Credentials sin login de
  usuario exige que la cuenta dueña de la app tenga Premium activo cuando
  la app está en Development Mode. Confirmado en vivo con `curl` directo a
  la API, no es un bug del código. Se destraba solo (sin tocar nada) el
  día que la cuenta tenga Premium.
- YouTube confirmado funcionando en vivo (búsqueda real, 5 resultados).
- **Shazam (reconocer canciones sonando) — implementado vía AudD**, no
  `shazamio`: esa librería depende de `shazamio-core` (Rust), que no tiene
  wheel prebuilt para Python 3.13 en Windows y falló al compilar acá
  (`link.exe` del toolchain de Rust no encuentra las libs de MSVC). AudD
  es una API REST simple (sin nada que compilar) — necesita
  `AUDD_API_TOKEN` (cuenta gratis en audd.io, sin tarjeta).
  - No es una tool de la IA: es un endpoint de subida directa,
    `POST /api/v1/music/identify` (`app/api/v1/music.py`), mismo criterio
    que `/voice/transcribe` y `/vision/analyze` — el usuario ya decidió
    explícitamente grabar el audio, no tiene sentido que pase por tool
    calling.
  - Botón "🎵 Shazam"/"🎵" agregado tanto al cliente de escritorio
    (`desktop/atlas_desktop/main.py`, graba 6s con `sounddevice`) como a la
    PWA móvil (`mobile/app.js`, graba 6s con `MediaRecorder`) — cualquiera
    de los dos clientes puede usarlo, no solo uno.
  - Pendiente de key propia (mismo criterio que YouTube/Spotify: sin
    `AUDD_API_TOKEN` configurada, el endpoint devuelve 400 con las
    instrucciones para conseguirla, en vez de romper en silencio).
- 15 tests backend nuevos (mockeando `requests`, sin pegarle a las APIs
  reales ni depender de tener las keys configuradas).

**Fase 11 (Recordatorios + rediseño del dashboard):**
- **Recordatorios** (`app/reminders/`): modelo + CRUD + API
  (`/api/v1/reminders`) y dos tools (`create_reminder`, `list_reminders`)
  para pedirlos por voz. Son distintos de las rutinas del Automation
  Engine a propósito: una rutina *ejecuta acciones*, un recordatorio solo
  *avisa*.
- **Métricas nuevas en `/api/v1/system/status`**: velocidad de red real
  (derivada entre dos muestreos de `psutil.net_io_counters`), uptime, y
  temperatura de CPU. La temperatura llega como `null` en equipos que no
  exponen el sensor (`psutil.sensors_temperatures` es solo Linux, y el
  fallback por WMI depende de que la placa exponga
  `MSAcpi_ThermalZoneTemperature` — la PC de desarrollo no lo hace); el
  dashboard oculta esa tarjeta en vez de inventar un número. El resultado
  de la detección se cachea: sin eso se abría una conexión WMI en cada
  sondeo, cada 4 segundos.
- **`ATLAS_USER_NAME`** en `.env` (vacío por defecto) para el saludo del
  dashboard, expuesto por `GET /api/v1/settings/profile`. Sin nombre
  configurado el saludo es genérico según la hora ("Buenos días").
- **Dashboard rediseñado** sobre un mockup del usuario: grilla de paneles
  (hero con orbe, Sistema con anillos + sparklines, Recordatorios,
  Dispositivos con filtro Todos/Salas/Tipos e interruptores,
  Acciones rápidas, Automatizaciones, Actividad como timeline, Estado de
  la casa) más una barra inferior de escucha a lo ancho. Vistas nuevas de
  Herramientas y Configuración.
- Se mantiene la regla de la Fase 9: **todo sale de datos reales de la
  API**. Los visualizadores de audio (orbe, ondas del hero, barra
  inferior) dibujan muestras reales del `AnalyserNode` mientras hay audio,
  y una línea plana en reposo — no hay animación decorativa fingiendo
  actividad. Las sparklines arrancan vacías y se llenan con cada sondeo.
- 20 tests backend nuevos. **`conftest.py` ahora fuerza a vacías las
  credenciales de integraciones**: sin eso los tests leían las reales de
  `.env` y salían a internet de verdad (detectado en vivo — un test le
  pegó a la API de AudD).

**Fase 12 (Smart home real vía Tuya):**
- `SMART_HOME_PROVIDER=tuya` (`app/smart_home/tuya_provider.py`), tercer
  provider junto a `mock` y `home_assistant`. Cubre las apps de marca
  blanca construidas sobre Tuya — **Mercury Smart** (la del usuario; su
  propio soporte recomienda la app de Tuya como alternativa), Smart Life,
  Tuya Smart, Geeni. Los mismos dispositivos vinculados a Alexa quedan
  cubiertos: Alexa es el control, no el dueño del aparato.
- **Por qué no se integró Alexa directamente**: Amazon no publica ninguna
  API para controlar dispositivos a través de Alexa — solo la Smart Home
  Skill API, que es para *fabricantes* que quieren aparecer en Alexa. Las
  librerías tipo `AlexaPy` son ingeniería inversa no oficial que se rompe
  sin aviso. Ir por Tuya alcanza el mismo hardware por la vía soportada.
- Usa el SDK oficial `tuya-connector-python` y no `requests` directo como
  `home_assistant_provider.py`: la firma HMAC-SHA256 de Tuya combina
  método, hash del cuerpo, headers, token, timestamp y nonce — fácil de
  implementar mal y difícil de depurar. El import es diferido, así que
  quien use mock/HA no necesita el SDK.
- Detalles que el provider resuelve y conviene no perder:
  - Tuya responde **HTTP 200 con `success: false`** en los errores — mirar
    el código de estado no alcanza.
  - El código del interruptor **varía por modelo** (`switch_led` en una
    bombilla, `switch_1` en una zapatilla): se descubre en vivo vía
    `/functions` en vez de asumir uno.
  - Las temperaturas llegan en décimas de grado como enteros (`215` =
    21.5 °C) y se normalizan a `capabilities["temperature"]`, el nombre
    que ya usa el resto de ATLAS.
  - El brillo se traduce entre el porcentaje de ATLAS y el rango 10–1000
    de Tuya.
  - **Las cerraduras se rechazan explícitamente**: abrirlas por API exige
    un flujo de contraseña temporal que no está implementado, así que se
    devuelve un error claro en vez de fingir que funcionó.
- `scripts/tuya_setup.py`: valida las credenciales, **encuentra solo el
  UID** de la cuenta vinculada (el dato más escondido de la consola de
  Tuya) y lista los dispositivos que ATLAS va a ver. Si falla, sugiere el
  centro de datos correcto, que es la causa más común.
- 16 tests, mockeando el SDK entero — no tocan la nube ni piden
  credenciales.

**Fase 13 (Gestos en el dashboard + set de iconos):**
- **El dashboard ahora captura gestos con la webcam de la propia PC**, no
  solo recibe los del celular. La primera versión de esta vista era solo un
  panel de estado, asumiendo que la cámara siempre estaría en el teléfono —
  pero eso fue circunstancial (la PC no tenía webcam el día que se probó).
  Se portó la detección de `mobile/app.js`: MediaPipe Tasks Vision en el
  navegador, mismos umbrales calibrados en vivo (`PINCH_RATIO`,
  `CURLED_RATIO`), y por el WebSocket solo viajan coordenadas — nunca video.
- **La cámara NO se apaga al cambiar de vista** (a diferencia de la PWA):
  el objetivo es manejar el mouse mientras mirás cualquier pantalla, así
  que apagarla al salir dejaba la función inservible. Solo la apaga el
  botón. Para que nunca quede corriendo en silencio, mientras captura se
  muestra un indicador rojo fijo en la barra superior, desde cualquier vista.
- `GET /api/v1/gestures/status` + `app/gestures/session.py`: el WebSocket no
  dejaba ningún rastro consultable — no había forma de saber si un celular
  estaba controlando el mouse salvo mirar si el cursor se movía. Ahora el
  dashboard muestra ambas fuentes (webcam local y teléfono) con datos reales.
- `GET /api/v1/settings/profile` devuelve también la **IP local**: el
  dashboard se abre en `127.0.0.1` y no puede saberla por su cuenta, pero la
  necesita para decir qué URL abrir en el celular.
- **Set de iconos SVG propio** reemplazando todos los emojis y glifos
  Unicode del dashboard. Dos motivos: los emojis rompían la identidad
  monocroma (pedido del usuario), y los glifos dependían de la fuente
  instalada — `⏻` y `◔` ya habían salido como cuadraditos vacíos en Segoe
  UI. Ahora el trazo hereda `currentColor` y se colorea por contexto.
- 9 tests nuevos (tracker de sesión + endpoints).

**Bug: en el celular no hablaba nunca** (clientes web)
- En móvil el permiso de autoplay **caduca**: nace del toque en "Enviar",
  pero el audio llega varios segundos después (respuesta de Claude +
  síntesis) y para entonces ya no vale. En escritorio casi no se nota; en
  celular no sonaba prácticamente nunca.
- Arreglado con el patrón estándar: **no se crea un `new Audio()` por
  respuesta**. Se reutiliza siempre el mismo elemento, desbloqueado en el
  primer gesto del usuario reproduciendo un WAV silencioso. Una vez
  desbloqueado se le puede cambiar el `src` sin gesto nuevo.
- En el dashboard esto además era obligatorio, no una mejora:
  `createMediaElementSource()` **solo puede llamarse una vez por elemento**,
  así que el grafo de audio del visualizador también se reutiliza.
- El elemento va **dentro del DOM**: algunos navegadores móviles solo
  reproducen de forma confiable elementos que están en el documento.
- Verificado en Chromium móvil simulado con
  `--autoplay-policy=user-gesture-required`.

**Bug: "a veces responde hablando y a veces no"** (los tres clientes)
- La causa **no era aleatoria, dependía de qué se pedía.** `speak()` se
  llamaba en un solo lugar: la respuesta directa del chat. Todo lo que pasa
  por el diálogo de confirmación (abrir/cerrar una app, mirar la pantalla,
  tocar un dispositivo — o sea las tools MEDIUM/HIGH_RISK) devolvía su
  respuesta final por otro camino, `resolveConfirmation`, que la mostraba
  pero nunca la hablaba. Corregido en dashboard, PWA y escritorio.
- **Segundo bug encontrado buscando el primero**: `playWithVisualizer`
  creaba un `AudioContext` sin reanudarlo. Un contexto nuevo arranca
  **suspendido** si no hubo un gesto del usuario reciente, y como el audio
  pasa *a través* del contexto para llegar a los parlantes, quedaba en
  silencio — sin que `audio.play()` fallara, así que no había ningún error
  visible. Ahora se reanuda, y si el navegador no lo permite se reproduce
  sin visualizador: es preferible oír a ATLAS sin la animación que tener la
  animación en silencio.
- Nota de método: el segundo bug **no se pudo reproducir** en Chromium bajo
  Playwright, que permite autoplay aun forzando la política. Se corrigió
  igual por ser incorrecto, pero el que explica el síntoma reportado es el
  primero, que sí es determinista y quedó verificado.

**Fase 19 (Búsqueda web — el hueco más grande que quedaba):**
- Hasta acá ATLAS no podía responder **nada actual**: noticias, precios,
  horarios, si algo pasó ayer. Wikipedia solo cubre temas enciclopédicos y
  el conocimiento del modelo se corta en su fecha de entrenamiento.
- Dos proveedores (`app/integrations/web_search.py`), mismo patrón que
  smart home y voz:
  - **`duckduckgo`** (por defecto): sin API key ni registro, anda al
    instante. Vía no oficial (`ddgs`): puede limitar por frecuencia.
  - **`tavily`**: además de enlaces devuelve una **respuesta ya
    sintetizada**, que le ahorra al modelo deducirla. 1.000 consultas/mes
    gratis con cuenta.
  - Brave quedó afuera: retiró su plan gratuito a fines de 2025.
- **La descripción de la tool es la parte que más importa.** Es la única
  señal que tiene el modelo para decidir cuándo buscar, cuándo ir a
  Wikipedia y cuándo responder de memoria. Está redactada alrededor de
  "¿depende de la fecha?" y hay un test que lo verifica — es fácil
  romperlo sin darse cuenta al editar el texto.
- Verificado en vivo: ante "noticias recientes de IA" eligió `search_web` y
  citó la fuente; ante "clima en Bogotá" eligió `get_weather`, que es la
  herramienta correcta. La selección entre tools funciona.
- 13 tests, mockeando la red.

**Fase 18 (Voz neuronal):**
- `TTS_PROVIDER=edge` (`app/voice/edge_provider.py`): las voces neuronales
  del navegador Edge, gratis y **sin API key**. Reemplazan a SAPI, que
  sonaba claramente sintética. Voz elegida tras comparar muestras de siete
  acentos: `es-MX-JorgeNeural` (configurable con `EDGE_TTS_VOICE`, más
  `EDGE_TTS_RATE` y `EDGE_TTS_PITCH`).
- **SAPI no se borró, y no es por nostalgia.** Edge tiene tres costos que
  SAPI no tenía: necesita internet, el texto sale de la máquina hacia
  servidores de Microsoft, y es una vía no oficial que podría dejar de
  funcionar sin aviso. `TTS_PROVIDER=sapi` sigue siendo la alternativa
  offline.
- Edge devuelve **MP3** pero el resto del proyecto habla WAV — el cliente
  de escritorio reproduce con `soundfile`. Se convierte dentro del
  proveedor para que ningún cliente se entere del cambio; alcanza con
  `soundfile` (libsndfile 1.2 lee MP3), sin ffmpeg ni dependencias extra.
- 11 tests, mockeando la red.

**Fase 17 (Wake word en todos los clientes + Markdown como texto enriquecido):**
- **`shared/`, primer código compartido entre los clientes web.** Hasta acá
  `dashboard/` y `mobile/` duplicaban todo, y eso ya había costado: al
  renombrar la palabra de activación hubo que tocarla en varios lugares.
  Ahora `shared/wake-word.js`, `shared/wake-processor.js` y
  `shared/markdown.js` viven una sola vez, y ambos `serve.py` los sirven en
  `/shared/` (con validación de ruta: escuchan en la red).
- **Wake word en el navegador** (`shared/wake-word.js`), port de
  `desktop/atlas_desktop/wake_word.py` con la misma estrategia: buffer
  deslizante, filtro de energía local y Whisper. Detalles que obligó el
  navegador:
  - **AudioWorklet y no MediaRecorder**: los fragmentos WebM no son
    decodificables por separado (solo el primero trae cabecera), así que no
    sirven para una ventana deslizante. Se captura PCM crudo y se arma el
    WAV a mano.
  - Corre en el hilo de audio, no en el principal: queda escuchando de
    forma continua y competiría con el renderizado de la interfaz.
  - Se **pausa mientras ATLAS habla** y se reanuda al terminar; sin eso su
    propia voz por los parlantes volvía a dispararlo.
  - Apagado por defecto: mantiene el micrófono abierto, así que tiene que
    ser una decisión explícita del usuario.
- **`ATLAS_WAKE_WORD` en `.env`**: la palabra la define el backend y la leen
  los tres clientes desde `/api/v1/settings/profile`. Antes vivía escrita en
  el código del escritorio, y agregarla a la web habría creado tres lugares
  donde desincronizarse.
- **Markdown ya no se lee ni se ve en crudo.** Dos mitades:
  - `backend/app/voice/markdown_speech.py`: limpia el Markdown **antes del
    TTS**, así el motor deja de leer "asterisco asterisco importante" y de
    dictar las URLs carácter por carácter. Está en el backend porque los
    tres clientes usan el mismo `/api/v1/voice/speak`.
  - `shared/markdown.js`: lo renderiza como texto enriquecido en las
    burbujas del chat. **Escapa el HTML primero, siempre** — el texto viene
    de un modelo que repite contenido de páginas web, memorias y
    dispositivos. Los enlaces se limitan a `http(s)`, así que un
    `[texto](javascript:…)` no se vuelve ejecutable.
- 20 tests nuevos del limpiador de Markdown.

**Fase 16 (Dashboard en la red local + Shazam en el dashboard):**
- `dashboard/serve.py` pasa a escuchar en `0.0.0.0` para poder entrar desde
  otro dispositivo. **HTTPS deja de ser opcional al hacerlo**: desde
  127.0.0.1 el navegador lo trataba como contexto seguro por sí solo, pero
  desde cualquier otra IP `getUserMedia` queda bloqueado sin certificado —
  se caerían el orbe de voz y el control por gestos.
- **Botón de Shazam en el dashboard**: estaba en el cliente de escritorio y
  en la PWA, pero faltaba acá. Pedírselo por chat nunca iba a funcionar y
  la respuesta del modelo era correcta: el reconocimiento de canciones **no
  es una tool de la IA** a propósito (subida directa, igual que
  `/voice/transcribe` y `/vision/analyze`), así que Claude no tiene acceso
  al micrófono.
- **Bug real encontrado al probarlo**: AudD usa `error_code 300` cuando no
  puede generar la huella del audio (silencio, clip corto, ruido). Se
  propagaba como excepción → 500 sin manejar → y como FastAPI no le agrega
  cabeceras CORS a un 500, **el navegador lo reportaba como error de CORS**,
  escondiendo el motivo real. Ahora ese código se trata como "no reconocí
  nada" (200 con `found: false`) y el resto de los errores de AudD devuelven
  502 (`AuddError`), que es lo honesto: falla el servicio externo, no ATLAS.
- Otra trampa del entorno: reiniciar el backend a mano deja procesos
  huérfanos: uvicorn con `--reload` es padre + hijo, y en Windows dos
  sockets pueden quedar ligados al mismo puerto — un backend viejo seguía
  respondiendo con código sin actualizar mientras el nuevo arrancaba en
  silencio. Al depurar, verificar **qué PID posee el puerto**, no solo que
  el puerto responda.

**Fase 15 (Paridad del cliente de escritorio con el dashboard):**
- La Fase 14 solo le aplicó *la pintura* del dashboard (paleta, tipografía,
  anillos, orbe) conservando la estructura de la Fase 4: una ventana de chat.
  Eso **no era un límite de Tkinter, fue un error de alcance** — CustomTkinter
  hace perfectamente barra lateral navegable, tarjetas e interruptores.
- Ahora tiene las **mismas 11 secciones** que el dashboard (Inicio,
  Conversación, Dispositivos, Automatizaciones, Recordatorios, Memoria,
  Gestos, Herramientas, Actividad, Notificaciones, Configuración), el hero
  con saludo por franja horaria y accesos rápidos, los mismos paneles de la
  home y la barra de escucha al pie.
- `atlas_desktop/views.py`: construcción y refresco de cada vista, separado
  de `main.py` (ventana, navegación, audio, sondeos) — juntos daban un
  archivo imposible de navegar. `api_client.py` gana los mismos endpoints
  que consume `dashboard/app.js`, para que ambas interfaces no se
  contradigan.
- **Lo que sigue difiriendo, y por qué**: sin SVG (los iconos del dashboard
  se sustituyen por barras de color por tipo de dispositivo); sin `rgba` ni
  degradados; sin `flex-wrap` (los chips van en grilla fija); animación por
  `after()` a ~25 fps; y el control por gestos necesita MediaPipe, que corre
  en un navegador — la vista de Gestos muestra el estado del receptor y
  dónde activarlo, no la captura.
- Tres trampas de CustomTkinter encontradas al probarlo en vivo:
  - `CTkFrame` ya define `_draw(no_color_updates=...)`; un widget propio que
    llame así a su método de dibujo lo pisa y revienta al construirse.
  - Un `CTkFrame` **sin hijos** conserva su alto por defecto (200 px): la
    barrita de color de cada fila estiraba la lista entera.
  - Un `CTkCanvas` no puede ser transparente; su `bg` tiene que coincidir
    exactamente con el del contenedor o se ve un rectángulo de otro tono.

**Fase 14 (Rediseño del cliente de escritorio):**
- `desktop/` pasa de la ventana funcional de la Fase 4 a la misma identidad
  visual del dashboard. **No puede quedar idéntica**: Tkinter no tiene CSS
  ni SVG, no admite canales alfa y sus Canvas no pueden ser transparentes.
  Lo que sí comparte: paleta, tipografía, jerarquía y estructura.
- `atlas_desktop/theme.py`: los mismos valores que `dashboard/styles.css`,
  como constantes de Python. Tkinter no tiene variables CSS y cada widget
  recibe sus colores a mano — tenerlos en un solo lugar evita que los dos
  clientes se vayan desincronizando.
- `atlas_desktop/widgets.py`: lo que en el dashboard resuelve el CSS acá
  hay que dibujarlo sobre Canvas — `MetricRing` (el `conic-gradient` de los
  anillos de CPU/RAM/Disco), `VoiceOrb` y `LevelBar`. Incluye un helper
  `_blend()` porque los `rgba()` translúcidos del dashboard hay que
  precalcularlos: Tkinter no tiene alfa.
- **Los visualizadores se mueven con audio real**, igual que en el
  dashboard: la amplitud sale del RMS de los bloques del micrófono
  (`_audio_level`), no de un temporizador. En reposo el orbe queda quieto y
  la barra muestra una línea plana, que es la verdad. Para que la voz de
  ATLAS también alimente el visualizador, `_play_speech` reproduce por
  bloques en vez de con `sd.play()` de una sola vez.
- `record_command_until_silence()` acepta un `on_level` opcional, para que
  el orbe también reaccione durante la captura del wake word.
- Dos bugs propios del entorno, encontrados al probarlo en vivo:
  - `CTkFrame` ya define un método `_draw(no_color_updates=...)` interno;
    llamar así al método de dibujo de un widget propio lo pisa y revienta
    al construirlo. Renombrado a `_render()`.
  - Un `CTkCanvas` no puede tener fondo transparente: si su `bg` no coincide
    exactamente con el del contenedor, se ve un rectángulo más claro
    alrededor del dibujo.

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
Para el modo wake word del cliente de escritorio, la palabra de activación
es "Ali" (antes "Atlas", luego "Vision").
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
