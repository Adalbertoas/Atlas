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
npm test                    # 96 pruebas unitarias
npm run typecheck
npm run build
npx electron .
```

Para chat y voz hace falta el backend (`python run.py` en `backend/`, puerto 8000) y la
variable `ATLAS_PASSWORD` en la terminal desde la que se lanza Electron. Sin backend el
núcleo funciona igual; el chat mostrará el aviso de conexión y el estado ERROR.

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
3. **Voz**: pulsa el micrófono del chat, habla y vuelve a pulsarlo. Verde turquesa con
   ondas entrantes mientras graba; la respuesta se lee en voz alta y el núcleo late con el audio.
4. **Manos**: *Configuracion → Neural Core → Control por manos (camara)* y acepta el aviso.
   Aparece el indicador rojo **Camara activa** con el botón **Apagar**.
5. **Depuración**: activa *Mostrar landmarks de depuracion* para ver el esqueleto de la mano,
   el número de manos, el tiempo de inferencia y el gesto activo.
6. **Sin cámara**: los botones *Probar pulso* y *Probar explosion* disparan los efectos.
7. **Recolocar nucleo** deshace los giros hechos con las manos.

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
| LISTENING | Verde turquesa | Ondas entrantes | El micrófono está grabando |
| THINKING | Violeta | Nube que se reorganiza | Petición `atlas:chat` en curso |
| PROCESSING | Blanco azulado | Movimiento acelerado | Transcribiendo o sintetizando voz |
| SPEAKING | Azul eléctrico | Pulsos con el audio | Está sonando la voz de ATLAS |
| SUCCESS | Verde | Pulso de confirmación (1,4 s) | Respuesta de chat recibida |
| ERROR | Rojo suave | Vibración controlada (2,6 s) | Fallo de chat, voz o cámara |
| SLEEPING | Azul tenue | Movimiento mínimo | 3 minutos sin actividad |

Prioridad: ERROR > SPEAKING > LISTENING > PROCESSING > THINKING > SUCCESS > SLEEPING > IDLE.
Los gestos modifican la geometría sin cambiar el estado, así que no interrumpen nada.

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
  voice/
    VoiceSession        grabar → transcribir → hablar, por IPC
  interaction/      Lo único que conoce a todos los demás.
    AtlasInteractionController  une cámara, audio, estados y preferencias con el motor
    AtlasVisualStateMachine     señales persistentes + pulsos temporales, por prioridad
    InteractionConfig           preferencias, saneado y persistencia
  ui/               React.
    ParticleCoreView, NeuralCoreHud, NeuralCoreSettings, CameraPermissionControl,
    HandDebugOverlay, useNeuralCore
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
- El micrófono solo se abre mientras se pulsa el botón de grabar. El audio va al backend local de
  ATLAS para transcribirse, igual que en el dashboard; el cliente no lo guarda.
- Sin telemetría. FPS e inferencia se muestran en pantalla y no salen de la aplicación.
- WASM y modelo se cargan desde `public/mediapipe/`, sin CDN en ejecución. El modelo
  (`hand_landmarker.task`, 7,5 MB, float16 v1) se descarga una vez desde
  `storage.googleapis.com/mediapipe-models`, el origen oficial de Google.

## Pruebas

**Unitarias** (`npm test`, 96 pruebas, todas pasan): mano abierta, puño, pinza, independencia de la
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
- Grabación con el micrófono, transcripción y voz contra el backend real. Los canales
  `atlas:transcribe` y `atlas:speak` compilan pero no se han ejecutado contra el backend.
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
- El consentimiento de cámara es de la aplicación: Electron no muestra un diálogo propio. La
  privacidad de Windows puede bloquear la cámara igualmente.
- `desktop/electron/` entero sigue sin estar bajo control de versiones en el repositorio.
