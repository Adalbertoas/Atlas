# ATLAS Neural Core

Núcleo holográfico de partículas 3D del cliente de escritorio (`desktop/electron`).
Reacciona a los estados reales de ATLAS, a la voz y, de forma opcional, a los gestos
de las manos captados por la webcam.

Implementado el 2026-10-13. Plan previo: [neural-core-plan.md](neural-core-plan.md).

## Cómo probarlo

Desde una terminal de VS Code:

```powershell
cd D:\Atlas\desktop\electron
npm install                 # solo la primera vez
npm run setup:mediapipe     # solo la primera vez: copia el WASM y descarga el modelo de manos
npm run setup:vad           # copia el runtime ONNX del detector de voz (también en predev/prebuild)
npm test                    # 146 pruebas unitarias
npm run typecheck
npm run build
npx electron .
```

Para chat y voz hace falta el backend (`python run.py` en `backend/`, puerto 8000) y la
variable `ATLAS_PASSWORD` en la terminal desde la que se lanza Electron. Si existe
`certs/dev-cert.pem`, Electron usa `https://127.0.0.1:8000` y confía solo en ese certificado
(antes intentaba `http://` y no llegaba nunca al backend HTTPS). `ATLAS_API_URL` y
`ATLAS_CERT_PATH` lo fuerzan. Sin backend el núcleo funciona igual; el chat mostrará el
aviso de conexión y el estado ERROR.

Dos avisos sobre el entorno:

- Si `npx electron .` falla con *"does not provide an export named 'BrowserWindow'"*, la
  terminal tiene `ELECTRON_RUN_AS_NODE=1`. Ejecuta `Remove-Item Env:ELECTRON_RUN_AS_NODE`.
- `npm run dev` espera el puerto 5173, que también usa la PWA móvil de `atlas.bat`, y
  `electron/main.ts` solo carga Vite si existe `VITE_DEV_SERVER_URL`. Para desarrollo en
  caliente: `$env:VITE_DEV_SERVER_URL="http://localhost:5173"; npm run dev` con la PWA parada.
  Esto ya era así antes de esta integración.

### Recorrido manual

1. **Núcleo**: al abrir, la esfera de partículas asoma detrás de los paneles. Pulsa
   **Ver nucleo** (abajo a la derecha) o `Ctrl+Shift+H` para apartar los paneles; `Esc` los devuelve.
2. **Estados**: escribe un mensaje. El núcleo pasa a violeta (pensando) y vuelve a cian.
   Con el backend parado se pone rojo unos segundos (error).
3. **Voz**: pulsa el micrófono del chat y habla. Lo que dices aparece en vivo sobre el cuadro
   de texto y se envía solo al callarte (pulsar otra vez lo envía ya). Verde turquesa con ondas
   entrantes mientras escucha; la respuesta se lee en voz alta y el núcleo late con el audio.
4. **Manos libres**: pulsa **Escuchar "Atlas"** en el indicador de abajo a la derecha (o
   *Configuracion → Neural Core · Voz*). Di *"Atlas, ¿qué hora es?"* de un tirón, o *"Atlas"*,
   una pausa y el pedido. Tras la respuesta hablada puedes seguir preguntando unos segundos sin
   repetir el nombre. **Apagar** en el indicador verde cierra el micrófono.
5. **Manos**: *Configuracion → Neural Core → Control por manos (camara)* y acepta el aviso.
   Aparece el indicador rojo **Camara activa** con el botón **Apagar**.
6. **Depuración**: activa *Mostrar landmarks de depuracion* para ver el esqueleto de la mano,
   el número de manos, el tiempo de inferencia y el gesto activo.
7. **Sin cámara**: los botones *Probar pulso* y *Probar explosion* disparan los efectos.
8. **Recolocar nucleo** deshace los giros hechos con las manos.

## Gestos

| Gesto | Acción |
|---|---|
| Mano abierta | Expande las partículas |
| Puño cerrado | Las contrae |
| Mover la mano a izquierda/derecha | Inclina el núcleo hacia ese lado (vuelve al soltar) |
| Mover la mano arriba/abajo | Lo inclina arriba o abajo (vuelve al soltar) |
| Separar ambas manos | Aumenta la expansión |
| Juntar ambas manos | Reconstruye la esfera (cancela una explosión) |
| Pinza índice–pulgar y arrastrar | Agarra el núcleo y lo gira libremente; se queda donde lo dejes |
| Soltar la pinza en movimiento | Sigue girando por inercia y se frena |
| Pinza con las dos manos y girarlas como un volante | Ladea el núcleo (giro sobre el eje que apunta al usuario) |
| Círculos sostenidos | Torbellino |
| Abrir ambas manos de golpe | Explosión, con reconstrucción automática |
| Manos fuera de cámara | Vuelve poco a poco al comportamiento automático |

Cada gesto pasa por **detectado → confirmado → sostenido → finalizado / perdido**. Los umbrales
tienen histéresis, hay un tiempo mínimo de activación y los gestos de un solo disparo tienen
cooldown (explosión 2,5 s, pinza 0,4 s). La *Sensibilidad de gestos* escala umbrales y tiempos, y
cada gesto se puede desactivar por separado.

Ningún gesto ejecuta herramientas: todos son efectos visuales. Si en el futuro se enlaza un
gesto a una acción real, el enlace debe marcarse `sensitive: true` en `GestureController`; esas
acciones no se ejecutan sin pasar por el callback `confirm` (hay una prueba que lo verifica).

## Estados visuales

| Estado | Color | Comportamiento | Evento real que lo activa |
|---|---|---|---|
| IDLE | Cian | Rotación suave | Ninguna otra señal activa |
| LISTENING | Verde turquesa | Ondas entrantes | Escuchando una frase dirigida a ATLAS (no mientras solo espera "Atlas") |
| THINKING | Violeta | Nube que se reorganiza | Petición `atlas:chat` en curso |
| PROCESSING | Blanco azulado | Movimiento acelerado | Transcribiendo o sintetizando voz |
| SPEAKING | Azul eléctrico | Pulsos con el audio | Está sonando la voz de ATLAS |
| SUCCESS | Verde | Pulso de confirmación (1,4 s) | Respuesta de chat recibida |
| ERROR | Rojo suave | Vibración controlada (2,6 s) | Fallo de chat, voz o cámara |
| SLEEPING | Azul tenue | Movimiento mínimo | 3 minutos sin actividad |

Prioridad: ERROR > SPEAKING > LISTENING > PROCESSING > THINKING > SUCCESS > SLEEPING > IDLE.
Los gestos modifican la geometría sin cambiar el estado, así que no interrumpen nada.

## Escucha en vivo

Dos formas de hablarle a ATLAS, con el mismo motor:

- **Micrófono del chat**: escucha un comando sin necesidad del nombre y lo envía al callarte.
- **Manos libres**: el micrófono queda abierto esperando *"Atlas"* al principio de una frase.
  Se activa por decisión explícita (no se guarda encendido; solo si se marca *Activar la
  escucha al abrir ATLAS*).

### Cómo decide qué escuchar

1. Un `AudioWorklet` entrega el micrófono en tramas de 20 ms a 16 kHz (con cancelación de eco,
   supresión de ruido y control de ganancia del navegador).
2. **Qué es voz lo decide un detector neuronal**, no el volumen: `SileroVad` (Silero VAD v6,
   ONNX, 1,2 MB, el mismo que trae faster-whisper) corre en el propio cliente con
   `onnxruntime-web` (WASM, un hilo, ~0,2 ms por bloque de 32 ms). Ventiladores, zumbidos,
   teclado, golpes, lluvia o música no cuentan aunque suenen fuerte, y la voz se detecta con
   ese ruido encima. `SpeechSegmenter` usa esa probabilidad (entra con 0,5, sigue con 0,35;
   ajustable con *Sensibilidad del microfono*) para marcar inicio y fin de cada frase. Si el
   modelo no carga, vuelve al detector por volumen (12 dB sobre el ruido de fondo medido).
   Conserva 300 ms antes del inicio para no cortar la primera sílaba y descarta golpes de menos
   de 200 ms.
3. `ListeningEngine` decide qué transcribir. Cada transcripción cuesta lo mismo (~650 ms en CPU
   con Whisper base, sea cual sea la duración: medido en esta máquina), así que:
   - en reposo, una frase solo se transcribe una vez (a ~1,1 s) para ver si empieza por
     "Atlas". Si no, se abandona: la conversación de fondo no consume más CPU;
   - mientras se le habla a ATLAS, una parcial cada ~0,9 s alimenta el texto en vivo;
   - a los 300 ms de silencio se transcribe **por adelantado**: si la frase termina ahí (800 ms
     de silencio), ese resultado ya es el final y no hay que esperar otra transcripción.
4. `wakeWord` acepta "Atlas" solo como primera palabra (tras "oye", "hola"…), con las formas en
   que Whisper lo oye mal (*hatlas*, *adlas*, *at las*…), y descarta las alucinaciones típicas
   de Whisper sobre ruido (*"Gracias por ver el video"*, *"Subtítulos realizados por…"*).
5. Mientras ATLAS piensa o habla, la escucha se pausa (no se oye a sí misma) e ignora 250 ms de
   eco al terminar.

En el backend, Whisper pasa además su propio filtro Silero (`vad_filter`): un clip que solo
tiene ruido sale vacío en ~10 ms en vez de ~650 ms y no se inventa texto sobre él (también
protege la voz del dashboard y la PWA).

**Ruido de fondo medido** (30 s por sonido, mismo corpus para los dos detectores):

| Sonido | Por volumen (antes) | Silero (ahora) |
|---|---|---|
| Golpes / platos | 11 frases falsas | 0 |
| Ventilador, zumbido, música, lluvia | 1 frase falsa de 4–5 s al abrir el micrófono | 0 |
| Teclado | 0 | 0 |
| Voz sola (6 frases) | 6/6 | 6/6 |
| Voz con ventilador | 4/6 (y 1 falsa) | 6/6 |
| Voz con música | **1/6** | **6/6** |
| Tele de fondo | 3 (es voz) | 3 (es voz: la filtra *Solo mi voz*) |

En Electron real, con 40 s de ventilador + música + golpes + zumbido **más fuerte que la voz**:
cero transcripciones durante 18 s de solo ruido, y *"Atlas, pon algo de música relajante"*
dicho encima se activó, se vio en vivo y se envió al callar.

El audio va al backend como WAV PCM16 a 16 kHz, que Whisper lee sin decodificar, con
`prompt="Hola Atlas."` para sesgar el vocabulario (probado sobre silencio, ruido blanco, golpes y
zumbido: no hace aparecer "Atlas" de la nada).

### Solo mi voz

En *Configuracion → Neural Core · Solo mi voz*, **Registrar mi voz** pide leer 3 frases (cada
una se graba sola y corta al terminar). El backend calcula una huella de voz y, desde entonces,
en manos libres ATLAS solo obedece a esa voz. El botón del micrófono no se filtra: pulsarlo ya
es una acción del usuario.

- **Modelo**: WeSpeaker ResNet34 (VoxCeleb, ONNX, 26 MB) sobre `onnxruntime`, que ya viene con
  faster-whisper: no hace falta PyTorch. El banco de filtros Mel estilo Kaldi que espera el
  modelo está reimplementado en numpy (`backend/app/voice/speaker.py`). Se descarga con
  `python scripts/download_speaker_model.py` (verifica el SHA-256) a `.cache/speaker/`.
- **Coste**: ~65 ms por frase. Con el filtro activo el backend compara la huella **antes** de
  transcribir: si la voz no es la registrada, Whisper ni se ejecuta (20–30 ms en vez de ~650 ms).
  La tele o una conversación cerca casi no gastan CPU y se ignoran sin avisos.
- **Decisión**: parecido (coseno) mayor o igual que la *Exigencia* (0,30–0,80; por defecto 0,50).
  La parcial que oye "Atlas" no activa nada si la voz no coincide; el comando tras "Atlas" y el
  seguimiento tras responder también se verifican. Si alguien dice "Atlas, …" con otra voz y
  llegó a transcribirse, el HUD avisa *Voz no reconocida (0,34)*. La puntuación de la última
  frase se ve en Configuración para ajustar la exigencia.

Calibración con las tres voces SAPI del sistema (registrar una, probar 8 frases de cada una):

| Registrada | Misma voz | Otras voces (máximo) |
|---|---|---|
| Sabina | 0,72 – 0,91 | 0,46 |
| David | 0,79 – 0,89 | 0,35 |
| Zira | 0,81 – 0,89 | 0,46 |

### Medido de punta a punta

Electron real con un WAV como micrófono (`--use-file-for-fake-audio-capture`), backend real
(Whisper base en CPU, Claude, voz SAPI), en esta máquina:

| Guion | Resultado |
|---|---|
| Conversación de fondo de 3 s sin "Atlas" | Ignorada: una sola transcripción, sin activación |
| *"Atlas, ¿qué hora es?"* de un tirón | LISTENING **antes de terminar la frase**; enviado **0,6 s** después de callar |
| *"Atlas."*, pausa de 1,2 s, *"¿Cuál es la capital de Francia?"* | Activado 0,7 s tras "Atlas"; texto en vivo; enviado **0,85 s** después de callar; respuesta hablada y escucha de seguimiento 5 s |
| Solo mi voz: registro con el asistente de la interfaz (3 frases, voz Sabina) | Huella guardada, coherencia 0,93 |
| Solo mi voz: *"Atlas, apaga la luz del salón"* (Zira) y *"Atlas, ¿cuál es la capital…?"* (David) | Ignoradas en silencio (0,12–0,34), **sin pasar por Whisper**: 19–27 ms por petición |
| Solo mi voz: *"Atlas, ¿qué hora es?"* (Sabina, registrada) | 0,69–0,76: activado mientras habla, enviado 1,1 s después de callar |
| Backend HTTPS con `certs/dev-cert.pem` | Transcripción, chat y voz funcionan |
| Backend HTTPS con otro certificado autofirmado (mismo nombre, otra clave) | Rechazado (`ERR_CERT_AUTHORITY_INVALID`); no llega ninguna petición |

Antes: botón para empezar y otro para terminar, sin texto en vivo ni palabra de activación; y
el webm que mandaba Electron **fallaba siempre** en el backend (faster-whisper 1.2.1 pasa a PyAV
19 un argumento que ya no existe; corregido en `backend/app/voice/whisper_provider.py`, lo que
arregla también la voz del dashboard y la PWA).

## Arquitectura

```
src/atlas/
  particle-core/    Motor. Solo depende de Three.js.
    ParticleCore        renderer, bucle, redimensionado, pérdida de contexto, limpieza
    ParticleAnimator    amortigua cada parámetro hacia su objetivo (sin saltos)
    ParticleShaders     vertex/fragment GLSL de partículas y halo
    ParticleMaterial    ShaderMaterial y volcado de uniforms
    ParticleGeometry    un BufferGeometry: una sola llamada de dibujo
    ParticleData        atributos por partícula (esfera, anillo, nube, semillas)
    ParticleEffects     halo y bloom opcional
    ParticlePresets     presets por estado y perfiles de calidad
    PerformanceMonitor  detección de caída sostenida de FPS
  hand-tracking/    Cámara y gestos. No conoce el núcleo.
    HandTrackingService cámara y ciclo de vida; envía fotogramas al worker
    handWorker          MediaPipe Hand Landmarker fuera del hilo de render
    LandmarkSmoother    filtro One Euro por coordenada
    handFeatures        apertura, pinza y centro, relativos al tamaño de la palma
    GestureRecognizer   señales continuas y presencia de cada gesto
    GestureStateMachine ciclo de vida, tiempo mínimo, cooldown, tolerancia a pérdidas
    GestureController   gestos → influencia sobre el núcleo y acciones
    GestureConfig       umbrales en función de la sensibilidad
  audio-reactive/   Audio. No conoce el núcleo.
    AudioAnalyzer       único AnalyserNode activo (micrófono o voz de ATLAS)
    audioFeatures       RMS, bandas, envolvente, detector de voz
    VoiceVisualizer     características → niveles suavizados 0..1
  voice/            Escucha en vivo. No conoce el núcleo.
    MicrophoneCapture   AudioWorklet → tramas PCM de 20 ms a 16 kHz
    pcm                 nivel en dB, remuestreo en flujo, WAV PCM16
    SileroVad           detector de voz neuronal en streaming (onnxruntime-web, WASM)
    SpeechSegmenter     inicio/pausa/fin de frase sobre el ruido de fondo medido
    wakeWord            "Atlas" al principio, variantes, alucinaciones de Whisper
    ListeningEngine     qué transcribir y cuándo; reposo, comando, pausa, seguimiento
    VoiceSession        micrófono + motor + IPC + reproducción
  interaction/      Lo único que conoce a todos los demás.
    AtlasInteractionController  une cámara, audio, estados y preferencias con el motor
    AtlasVisualStateMachine     señales persistentes + pulsos temporales, por prioridad
    InteractionConfig           preferencias, saneado y persistencia
  ui/               React.
    ParticleCoreView, NeuralCoreHud, NeuralCoreSettings, CameraPermissionControl,
    ListeningSettings, HandDebugOverlay, useNeuralCore
```

```
Cámara → HandTrackingService → LandmarkSmoother → GestureRecognizer
       → GestureStateMachine → GestureController ─┐
Micrófono / voz de ATLAS → AudioAnalyzer → VoiceVisualizer ─┤
Eventos reales (chat, voz) → AtlasVisualStateMachine ───────┤
                                                            ▼
                             AtlasInteractionController → ParticleCore (GPU)
```

Las dependencias van en un solo sentido: `particle-core`, `hand-tracking` y `audio-reactive` no
se importan entre sí; `interaction` las compone; `ui` solo habla con `interaction`.

Toda la animación por partícula ocurre en el vertex shader. La CPU envía unos 25 uniforms por
fotograma. Las formas (esfera, anillo, nube, torbellino, explosión, pulso) son pesos continuos,
así que todas las transiciones son reversibles.

Uniforms: `uTime`, `uExpansion`, `uRotation`, `uGestureStrength`, `uAudioLevel`, `uAudioBass`,
`uAudioMid`, `uAudioTreble`, `uEmotion`, `uInteractionPoint`, `uInteractionStrength`,
`uExplosionProgress`, `uPulse`, `uRing`, `uCloud`, `uVortex`, `uVortexPhase`, `uWavePhase`,
`uWaveStrength`, `uJitter`, `uSize`, `uScale`, `uColorA`, `uColorB`, `uBrightness`.

### Cambios en archivos existentes

- `src/main.tsx`: monta `ParticleCoreView` y `NeuralCoreHud`, añade la sección **Neural Core** a
  Configuración, conecta el botón de micrófono y sustituye el temporizador `speaking` de 950 ms por
  el estado real. `Toggle` y `Range` pasan a `src/components/Controls.tsx`.
- `electron/main.ts`: canales `atlas:transcribe` y `atlas:speak` (reenvían a `/api/v1/voice/*` con
  la sesión del chat) y un `setPermissionRequestHandler` que solo concede cámara y micrófono a la
  ventana de ATLAS. Antes Electron concedía cualquier permiso.
- `package.json`: dependencia `@mediapipe/tasks-vision` y scripts `test`, `typecheck`,
  `setup:mediapipe`, `predev`, `prebuild`.

No se tocó el backend, el dashboard, la PWA móvil, `integrations/`, los `.blend` ni `Hologram.tsx`.

## Calidad y rendimiento

| Nivel | Partículas | Pixel ratio máx. | Ruido simplex | Bloom |
|---|---|---|---|---|
| Baja | 2.500 | 1 | No | No |
| Media | 6.000 | 1,5 | Sí | No |
| Alta | 12.000 | 2 | Sí | Opcional |

En **Automática** se parte de Media (Baja si el render es por software) y nunca se sube a Alta
sola. Si los FPS caen por debajo de 42 durante 4 s seguidos, baja un nivel. Con la calidad fijada
a mano no se cambia nada: el HUD lo sugiere con un botón.

El render se pausa con la ventana oculta. La inferencia de manos corre en un **worker**
(`handWorker.ts`), con un máximo de 20 Hz y su propio temporizador: no bloquea el render. Usa el
delegado de CPU por defecto; `?handDelegate=GPU` en la URL lo cambia para diagnóstico. Si el worker
no arranca, se usa el hilo principal.

### Mediciones

Electron 40.10.6, ventana 1536×960, **Intel UHD Graphics 630** (integrada), Windows 10. Medido con
la prueba de humo automatizada, sin cámara ni backend.

| Calidad | FPS (conteo de fotogramas) | Envío de render en CPU |
|---|---|---|
| Baja, 2.500 | 60,2 | 0,14 ms |
| Media, 6.000 | 58,7 – 60,2 | 0,17 ms |
| Alta, 12.000 | 60,2 | 0,16 ms |
| Alta + bloom | 60,1 | 0,44 ms |

- Memoria con el núcleo activo: proceso renderer 121 MB, proceso GPU 263 MB, heap JS 10 MB.
- Carga de WASM + modelo de manos desde disco: 450 ms.

Con la cámara real encendida (FHD Camera, 640×480 a 30 fps), 45 s moviendo las manos:

| Inferencia | FPS del núcleo (media / mínimo) | Inferencia p50 / p90 | Frecuencia | Encendido |
|---|---|---|---|---|
| Hilo principal, GPU (primera versión) | 44 / 37 | 64 / 81 ms | 14,6 Hz | 6,5 s |
| Worker, GPU (sin manos en cuadro) | 55 / 34 | 28 / 33 ms | 15,4 Hz | 1,8 s |
| **Worker, CPU (predeterminado)** | **60 / 60** | 84 / 107 ms | 12,2 Hz | 1,8 s |

Sin manos en cuadro el worker en CPU infiere en 49 ms (19,5 Hz). Con manos baja a unos 12 Hz: es
el precio de mantener el render a 60 FPS en una gráfica integrada.
- FPS tras perder y recuperar el contexto WebGL: 60,1.

Los FPS están limitados por la sincronización vertical (60 Hz), así que no indican cuánto margen
queda. El tiempo de render es solo el envío desde la CPU, no el trabajo de la GPU.

**No medido:** latencia de extremo a extremo de un gesto, uso de CPU (la API de Electron devolvió 0 % en la única muestra, que no es válida) y uso de GPU.

## Privacidad

- La cámara está apagada al abrir ATLAS, siempre. El control por manos no se guarda entre sesiones.
- Activarla exige aceptar un aviso explícito; hay un indicador visible y un botón de apagado inmediato.
- Los fotogramas se procesan en el propio proceso con MediaPipe y se descartan. No se guardan ni
  se envían. Lo único que sale del servicio son coordenadas.
- El micrófono se abre al pulsar su botón y se cierra al enviar. Con **manos libres** queda abierto,
  pero solo tras activarlo de forma explícita, con un indicador verde visible y **Apagar**. No se
  guarda encendido entre sesiones salvo que se marque *Activar la escucha al abrir ATLAS*.
- El sonido se analiza en el equipo. Solo las frases con voz van al backend local de ATLAS para
  transcribirse, igual que en el dashboard; nada se guarda. En reposo, una frase que no empieza
  por "Atlas" se transcribe una sola vez y se descarta.
- **Huella de voz**: es un dato biométrico. Se guarda solo como un vector de 256 números en
  `backend/speaker_profile.json` (fuera de git), nunca el audio de las frases de registro, y
  **Borrar mi voz** la elimina. Se calcula y se compara en el equipo.
- Electron confía en el certificado autofirmado de `certs/dev-cert.pem` solo si coincide exacto y
  solo para el host del backend.
- Sin telemetría. FPS e inferencia se muestran en pantalla y no salen de la aplicación.
- WASM y modelo se cargan desde `public/mediapipe/`, sin CDN en ejecución. El modelo
  (`hand_landmarker.task`, 7,5 MB, float16 v1) se descarga una vez desde
  `storage.googleapis.com/mediapipe-models`, el origen oficial de Google.

## Pruebas

**Unitarias** (`npm test`, 146 pruebas, todas pasan; backend `pytest`, 218). Ruido de fondo
(8, con el modelo Silero real sobre una frase grabada y ruido sintético fuerte): el ruido no es
voz, la voz sí, la frase se detecta entera con ruido encima, histéresis, sensibilidad, y el motor
no transcribe nada durante 8 s de ruido pero sí el comando dicho encima. Solo mi voz (7 en
el cliente, 11 en el backend): voz registrada obedecida, otra voz ignorada con y sin
transcripción, comando ajeno tras mi "Atlas", seguimiento verificado, botón sin filtrar, voz no
verificable, fbank, registro sin audio guardado, endpoints. Escucha en vivo (35): WAV, remuestreo,
tramas, inicio/pausa/fin de frase, pausas entre palabras, clics, ruido de fondo alto, duración
máxima, "Atlas" de un tirón, "Atlas" y pausa, comando empezado antes de que llegue la
transcripción de "Atlas", conversación de fondo, "atlas" a mitad de frase, botón sin palabra,
transcripción anticipada reutilizada o descartada, silencio, golpes, pausa durante la respuesta,
eco, seguimiento, fallos del backend, variantes y alucinaciones de Whisper. Resto (96): mano abierta, puño, pinza, independencia de la
distancia, suavizado, tiempo mínimo de activación, cooldown, tolerancia a pérdidas, torbellino,
explosión, separación de manos, sensibilidad, confirmación de acciones sensibles, prioridades de
estado, pulsos temporales, RMS, bandas, envolvente, detector de voz, perfiles de calidad,
transiciones sin saltos, explosión reversible, monitor de rendimiento, saneado de preferencias.

**Prueba de humo en Electron real** (ventana real, IPC sustituido por respuestas de prueba):

| Comprobación | Resultado |
|---|---|
| ATLAS arranca sin cámara y el núcleo aparece | Pasa |
| Paneles, barra lateral y dock siguen presentes | Pasa |
| Enviar un mensaje activa THINKING | Pasa |
| La respuesta hablada activa PROCESSING → SPEAKING → IDLE | Pasa |
| El núcleo analiza el audio que suena (RMS pico 0,26) | Pasa, con un WAV sintético |
| Un fallo de chat activa ERROR y luego vuelve a IDLE | Pasa |
| Los gestos modifican las partículas | Pasa, con landmarks sintéticos inyectados |
| Sin manos vuelve al estado automático | Pasa |
| Cambio de calidad en caliente y bloom | Pasa |
| Pérdida y recuperación del contexto WebGL | Pasa |
| Desactivar partículas libera el motor; reactivar lo recrea | Pasa |
| WebGL no disponible: ATLAS sigue funcionando y lo avisa | Pasa |
| WASM y modelo de manos se cargan en local | Pasa |
| Cámara real: mano abierta, puño, pinza, círculos, separar y juntar manos | Pasa |
| Cámara real: rotar con la mano, expansión 0,56–1,45, torbellino | Pasa |
| Cámara real: al apagar, la pista de vídeo queda liberada | Pasa |
| Sin errores de consola en el flujo normal | Pasa |

**No se pudo probar** y queda para la prueba manual:

- **Agarrar y girar**, la inercia y el volante a dos manos con manos reales: cubiertos por 9 pruebas
  unitarias, pero en la sesión de prueba con cámara no hubo manos en cuadro.
- El gesto de **explosión** con manos reales: no llegó a dispararse en tres sesiones de prueba. La
  lógica está cubierta por pruebas unitarias con landmarks sintéticos, pero no confirmada con cámara.
- **Solo mi voz con voces humanas reales**: calibrado y probado con voces sintéticas, que son
  más constantes que una persona (resfriado, cansancio, otro micrófono). Falta ver qué
  puntuación da tu voz real y si 0,50 es la exigencia adecuada; también con voces parecidas
  (familiares).
- La escucha con **un micrófono y una voz reales**: la prueba de punta a punta usa voz sintética
  (SAPI) inyectada como micrófono, sin eco de altavoces ni ruido de una sala real. Falta
  confirmar la sensibilidad por defecto, el cancelador de eco con altavoces y que no se active
  con la tele o una conversación cerca.
- LISTENING y SLEEPING por su vía real; solo se verificó su aspecto forzando la señal.
- Cámara o micrófono desconectados en caliente, permiso denegado, cambio de dispositivo de audio.
  El código los maneja, pero no se han provocado.
- Fallo al cargar MediaPipe.

## Limitaciones

- En la disposición inicial el panel de chat tapa el centro del núcleo; asoma por arriba y por
  los lados. Para verlo entero: **Ver nucleo**, o mover el chat.
- La pinza marca un punto y atrae partículas, pero el núcleo no tiene todavía elementos
  seleccionables.
- Con manos en cuadro la inferencia en CPU va a unos 12 Hz; el movimiento se interpola, pero los
  gestos rápidos responden con algo de retardo.
- Cuando la respuesta se lee en voz alta, el pulso de SUCCESS queda tapado por PROCESSING y SPEAKING.
- Tras perder y recuperar el contexto WebGL, al desmontar el núcleo Chromium escribe avisos
  `delete: object does not belong to this context`. Son inofensivos.
- El chat de Electron no usa streaming, así que la voz empieza cuando llega la respuesta completa.
- El detector de voz no distingue tu voz de la de la tele o de otra persona: eso lo hace *Solo
  mi voz*. Sin voz registrada, la tele o una conversación cerca siguen contando como voz (en
  reposo se descartan si no empiezan por "Atlas").
- Con ruido muy fuerte encima, Whisper puede equivocarse en alguna palabra (en la prueba oyó
  "con" por "pon").
- La palabra de activación usa Whisper, no un motor dedicado: cada frase en reposo cuesta una
  transcripción (~650 ms de CPU) y reacciona ~0,7 s después de "Atlas". Un motor dedicado
  (openWakeWord) sería más barato, pero no trae un modelo para "Atlas" en español.
- El seguimiento tras responder acepta cualquier frase durante 5 s, también una de fondo. Se
  puede desactivar en *Seguir escuchando tras responder*.
- La verificación de voz no distingue una grabación de tu voz de tu voz en directo, y una voz
  muy parecida a la tuya puede superar el umbral. Es una barrera contra la tele y otras
  personas, no un control de seguridad: las acciones sensibles siguen pidiendo confirmación.
- No se puede interrumpir a ATLAS hablando con la voz (la escucha se pausa para no oírse a sí
  misma); sí con el botón del micrófono o **Silenciar**.
- El consentimiento de cámara es de la aplicación: Electron no muestra un diálogo propio. La
  privacidad de Windows puede bloquear la cámara igualmente.
- `desktop/electron/` entero sigue sin estar bajo control de versiones en el repositorio.
