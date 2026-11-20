# Integración del humanoide de partículas en ATLAS

Fecha: 20-nov-2026 · Rama: `feature/world-reminders-briefing` · Laboratorio de origen: `D:\Desktop\ATLAS_3D\particles\` (Fase 5)

## Resumen

El humanoide de partículas de la Fase 5 ya funciona dentro de la **aplicación de escritorio real de ATLAS** (Electron). Ocupa el lugar del Neural Core anterior, detrás de los paneles. Funciona con:

- el GLB V004 y 16.384 / 65.536 / 131.072 partículas;
- animaciones y núcleo de energía;
- bloom;
- la voz real de ATLAS (micrófono y TTS);
- la cámara de ATLAS (manos con MediaPipe).

No hay un dashboard nuevo, ni otro sistema de voz, ni otra cámara. El humanoide recibe estados, audio y manos del controlador que ya existía (`AtlasInteractionController`).

El núcleo anterior **no se borró**:

- sigue disponible en *Configuración → Neural Core → Figura central*;
- se usa solo si el humanoide no puede cargarse (sin WebGL2 o sin recursos).

## 1. Ruta real de la aplicación

| Ruta | Qué es | Decisión |
|---|---|---|
| `D:\Atlas` | Repositorio git real (`origin` = GitHub `Adalbertoas/Atlas`), con backend, escritorio, tablet y despliegue. | **Repositorio de trabajo** |
| `D:\Atlas\desktop\electron` | Aplicación principal de escritorio: Electron 40, React 19, Three r180, Neural Core, voz y cámara. | **Aquí se integró** |
| `D:\Desktop\Atlas` | Solo `.git\objects`, sin `HEAD`, refs ni copia de trabajo. Último commit: 22-sep-2026 («respaldo antes de integrar JARVIS»). El `dashboard/app.js` con `Atlas3D` que mencionan los informes de la Fase 5 solo existe ahí, en árboles sueltos de git. | No usable como app; no se tocó |
| `D:\Atlas\dashboard` | Cliente web sencillo (`app.js` de 1.137 líneas), sin Three.js, sin avatar y sin `Atlas3D`. | No es donde vive el humanoide |
| `C:\Users\ADALBERTO\AppData\Local\Programs\ATLAS` | Instalación empaquetada (el acceso directo `ATLAS.lnk`), compilada el **14-oct-2026**. | Desactualizada; ver §8 |

La elección de `D:\Atlas\desktop\electron` la confirmó el usuario el 20-nov-2026.

**El contrato `Atlas3D`** se respetó tal cual:

- `new AtlasParticle3D(container)`, `.setState()`, `.setAudioSamples(Uint8Array)` y `.dispose()`;
- el evento `atlasstatechange` y el atributo `data-state`.

Como esta app no tiene `app.js`, el adaptador lo usa un envoltorio TypeScript (`HumanoidCore`). Ese envoltorio hace en Electron lo mismo que hacía `app.js` en el dashboard viejo.

## 2. Arquitectura

### Antes

```
main.tsx ─ useNeuralCore() ─ AtlasInteractionController (único dueño de voz, cámara y estados)
                                  ├─ VoiceSession / AudioAnalyzer  (micrófono, manos libres, TTS)
                                  ├─ HandTrackingService (MediaPipe local, worker) → GestureController
                                  ├─ AtlasVisualStateMachine  (IDLE, LISTENING, THINKING, …)
                                  └─ ParticleCore (Three r180)  ← esfera de partículas
ParticleCoreView → <canvas> → runtime.attachCore(canvas)
Chat: atlas:chat → POST /api/v1/chat (sin streaming: no se sabía cuándo se ejecutaba una herramienta)
```

### Después

```
main.tsx ─ useNeuralCore() ─ AtlasInteractionController (sigue siendo el único dueño)
                                  ├─ VoiceSession / AudioAnalyzer ──(timeDomain: Uint8Array)──┐
                                  ├─ HandTrackingService ──(mismos fotogramas)───────────────┐ │
                                  ├─ AtlasVisualStateMachine (+ EXECUTING) ──(estado)──────┐ │ │
                                  ├─ ParticleCore (núcleo anterior: opción / plan B)       │ │ │
                                  └─ HumanoidCore  ◄───────────────────────────────────────┴─┴─┘
                                        └─ AtlasParticle3D (laboratorio, sin cambios, Three r164)
                                              └─ AtlasParticleAvatar → motor, animación, gestos, AtlasCore, bloom
ParticleCoreView → HumanoidLayer → runtime.attachAvatar(div)   (o CoreCanvas si avatar = "core")
Chat: atlas:chat → POST /api/v1/chat/stream → eventos "tool" / "tool_done" → estado EXECUTING
```

Reglas de diseño:

- **Una sola figura a la vez.** `attachAvatar` y `attachCore` desmontan antes cualquier otra.
- **Un solo `requestAnimationFrame`.** `HumanoidCore` lee el estado y el audio dentro del bucle del propio humanoide (envolviendo `avatar.update`), así que se pausa con la ventana oculta y con el contexto WebGL perdido.
- **Ningún estado inventado.** Cada estado sale de un evento real (tabla de §5).

## 3. Archivos copiados (sin modificar)

| Origen (laboratorio) | Destino |
|---|---|
| `particles/src/**` (29 archivos) | `desktop/electron/src/atlas/humanoid/particles/src/` |
| `particles/vendor/**` (Three r164, GLTFLoader, postprocessing, gesture-engine…) | `desktop/electron/src/atlas/humanoid/particles/vendor/` |
| `blender/exports/ATLAS_humanoid_v004.glb` (SHA-256 `1007ee02…1e51292`) | `desktop/electron/public/assets/atlas/` |
| `particles/data/atlas_v004_particles.bin` / `.json` | `desktop/electron/public/assets/atlas/` |

- `src` y `vendor` están juntos, así que los `import` relativos siguen igual. Se usa la copia local de Three r164, sin descargas ni otras versiones.
- `diff -r` contra el laboratorio: idénticos. La única diferencia es el archivo nuevo `AtlasParticle3D.d.ts`.
- El GLB copiado conserva su SHA-256, y no se tocaron los archivos de Blender.
- Respaldo previo de todo lo modificado: `D:\Atlas-backups\humanoide-2026-11-20\` (`antes_integracion.tgz` y `styles.css.antes`).

## 4. Archivos nuevos y modificados

### Nuevos

| Archivo | Para qué |
|---|---|
| `src/atlas/humanoid/HumanoidCore.ts` | Envuelve `AtlasParticle3D`. Tiene la misma interfaz que `ParticleCore` (calidad, bloom, estadísticas, degradación, pérdida de contexto) y además: puente de manos, pixel ratio dinámico y `data-state` inicial. |
| `src/atlas/humanoid/humanoidBridge.ts` | Funciones puras: estado de ATLAS → estado del humanoide, cuándo el audio lo mueve, calidad, landmarks sin espejo. |
| `src/atlas/humanoid/humanoidBridge.test.ts` | 9 pruebas unitarias. |
| `src/atlas/humanoid/particles/src/integration/AtlasParticle3D.d.ts` | Tipos para usar el adaptador JS desde TypeScript. |
| `public/assets/atlas/*` | GLB y datos de partículas. |

### Modificados

| Archivo | Cambio |
|---|---|
| `src/atlas/interaction/AtlasInteractionController.ts` | `attachAvatar()`, `humanoidCanvas`, `snapshot.humanoid`, `assistant.toolStarted/toolFinished`, `provideHumanoidFrame()`, manos y calidad/bloom hacia el humanoide; reintento al volver a elegirlo. |
| `src/atlas/interaction/AtlasVisualStateMachine.ts` | Estado **EXECUTING** (prioridad 45, entre THINKING y PROCESSING) con la etiqueta «Ejecutando». |
| `src/atlas/interaction/InteractionConfig.ts` | Ajustes `avatar: "humanoid" \| "core"` (por defecto, humanoide) y `avatarBloom` (por defecto activado), validados. |
| `src/atlas/particle-core/ParticlePresets.ts` | Preset `executing` para el núcleo anterior (igual que `processing`). |
| `src/atlas/audio-reactive/AudioAnalyzer.ts` | `timeDomain()`: muestras `getByteTimeDomainData` del audio activo (TTS con prioridad, si no el micrófono). |
| `src/atlas/ui/ParticleCoreView.tsx` | `HumanoidLayer` en la misma capa (`.neural-core-layer`), con el núcleo anterior como opción y plan B. |
| `src/atlas/ui/NeuralCoreSettings.tsx` | «Figura central», densidades del humanoide y «Bloom (apágalo si va lento: el núcleo del pecho se mantiene)». |
| `src/atlas/ui/useNeuralCore.ts` | Escucha `atlas:chat-event` (tool / tool_done). |
| `src/main.tsx` | Al aprobar una acción pendiente: `requestStarted` y `toolStarted`, porque el backend la ejecuta en ese momento. |
| `src/vite-env.d.ts` | Tipo de `window.atlas.on`. |
| `src/styles.css` | Corrección de un desborde que ya existía con el zoom en ventanas pequeñas (§7, punto 5). |
| `src/atlas/interaction/interaction.test.ts` | Cuenta 9 estados (antes 8). |
| `electron/main.ts` | El chat usa `/api/v1/chat/stream` (si el backend no lo tiene, vuelve a `/api/v1/chat`) y reenvía `tool` y `tool_done` a la ventana. |
| `electron/preload.cts` | `window.atlas.on(canal, fn)`, solo para `atlas:chat-event` (lista blanca). |
| `backend/app/core/orchestrator.py` | Evento de streaming `tool_done` (con `success`) después de ejecutar cada herramienta. |
| `backend/app/api/v1/chat.py` | Serializa `tool_done`. |
| `backend/tests/test_streaming.py`, `test_orchestrator.py` | Esperan `tool_done`. |

## 5. Importaciones sustituidas y conexiones

**La importación** que en el dashboard viejo era `import("./js/atlas-3d.js") → new Atlas3D(container)` aquí es:

```ts
// src/atlas/humanoid/HumanoidCore.ts
import { AtlasParticle3D } from "./particles/src/integration/AtlasParticle3D.js";
this.view = new AtlasParticle3D(container, { glbUrl, dataUrl, quality, bloom, camera, onready, onerror });
```

`ParticleCoreView` monta `HumanoidLayer → runtime.attachAvatar(div)` en lugar de `CoreCanvas → runtime.attachCore(canvas)`. Esto aplica cuando `avatar = "humanoid"`, que es el valor por defecto.

### Estados

| Evento real en ATLAS | Estado visual | Humanoide | Cuerpo / núcleo |
|---|---|---|---|
| Nada en curso, reposo de 3 min o pulso de éxito | IDLE / SLEEPING / SUCCESS | `idle` | Idle |
| Micrófono grabando (botón o comando tras «Atlas») | LISTENING | `listening` | Listening |
| Petición al backend en curso | THINKING | `thinking` | Thinking |
| Transcribiendo o sintetizando voz | PROCESSING | `thinking` | Thinking |
| Evento `tool` del streaming, hasta `tool_done` | **EXECUTING** | `executing` | Explaining (en bucle) |
| Suena la voz de ATLAS | SPEAKING | `speaking` | Talking + asentimiento |
| Petición fallida o error de micrófono o cámara (pulso de 2,6 s) | ERROR | `error` | Idle (regla del laboratorio) |

### Audio

- `AudioAnalyzer.timeDomain()` entrega el mismo `Uint8Array` que usaba `app.js`.
- **Solo mueve al humanoide en `listening` y `speaking`.** Con manos libres el micrófono queda abierto, y el ruido de fondo no debe animarlo. Medido: nivel 0,008 en reposo.

### Manos

- La única cámara es la de ATLAS, con su `HandTrackingService` y MediaPipe local (sin CDN).
- Sus fotogramas pasan por `AppHandProvider` hacia el `HandTracker` del laboratorio. Antes se deshace el espejo de la app, porque el seguimiento espera las coordenadas crudas de MediaPipe.
- Al apagarse la cámara se llama a `disableHandInput()` y se sueltan los gestos L y R: no queda ninguno puesto.
- El `MediaPipeHandProvider` del laboratorio, que usa la CDN, **no se usa**.

### Voz

No se usan `VoiceSession` ni `AtlasBackendProcessor` del laboratorio. Se verificó que `avatar.voiceSession` vale `null`.

## 6. Pruebas ejecutadas

Todas las pruebas se hicieron sobre la app real compilada (`dist/`), manejada por CDP con perfiles de prueba en `D:\Atlas-e2e\appdata\` para no tocar las preferencias del usuario. Los scripts están en `D:\Atlas-e2e\humanoid\` y los resultados (JSON y capturas) en `docs/integracion_humanoide/`.

**Equipo de prueba:**

- GPU Intel UHD Graphics 630 (ANGLE / D3D11), pantalla a 1x.
- La CPU estaba muy cargada durante las pruebas: dos backends, VS Code y otros procesos. La captura 10 muestra `cpu_percent: 100`.

| Prueba | Resultado |
|---|---|
| Unitarias del escritorio (`npm test`) | **160/160**, de las cuales 9 son nuevas del humanoide |
| `tsc` del renderer y del proceso principal | Sin errores |
| Backend (`pytest`) | **323/323** |
| Arranque de la app | Humanoide listo en **2,9 s**; 1 capa, 1 lienzo; 0 errores de consola |
| Crear y destruir (6 cambios humanoide ↔ núcleo) | Siempre **1** capa y **1** lienzo; heap de JS de 33,5 → 33,5 MB |
| Partículas desactivadas | 0 capas, 0 lienzos |
| Cierre de la ventana | El proceso termina con código 0 en ~0,5 s |
| Duplicados (`getUserMedia`, AudioContext, WebGL) | Micrófono 1, cámara 1, AudioContext 1 y contexto WebGL 1; voz del laboratorio `null`; manos por el proveedor «ATLAS» |
| Pérdida y recuperación de WebGL (`WEBGL_lose_context`) | `core: context-lost` → `ok`; 1 pérdida y 1 recuperación; 53,7 FPS después |
| Redimensionado real de la ventana (1080×700, 1280×800, 1920×1040, 1536×960; con y sin paneles) | El búfer del lienzo es igual a la capa y termina en el borde de la ventana en los 8 casos |
| Pixel ratio 1,5 / 2 / 1,25 / 1 | El lienzo se reajusta: 2031×1231, 2708×1642, 1692×1026, 1354×821 |
| Voz por manos libres (WAV: «Atlas» … «¿qué hora es?») | Transcripción → chat → `tool get_current_time` → **executing** → `tool_done` → thinking → synthesizing |
| Botón del micrófono | listening (clip Listening, nivel del micrófono: media 0,034) → thinking → **speaking** (clip Talking, nivel de la voz: máximo 0,43) → escucha de seguimiento → idle |
| Audio de TTS real (Kokoro) | Nivel del humanoide igual al pico del analizador: máximo 0,51, media 0,11 |
| Chat escrito con herramienta («dame el estado del sistema») | `tool get_system_info` → **executing ~360–580 ms** (lo que dura la herramienta) → thinking → speaking |
| Error real (backend inaccesible) | thinking → **error** (núcleo error, cuerpo Idle, `data-state="error"`) → idle al vencer el pulso |
| Cámara con manos (vídeo simulado con la mano renderizada del GLB) | Una mano: la R del usuario pasa a la L del avatar (espejo), «Open» y clip **Waving**. Dos manos: el avatar refleja las dos. Sin manos: se sueltan. Al apagar la cámara: proveedor detenido y sin gestos. |

El ciclo de voz, chat y herramienta se probó contra un **backend de prueba** en `:8767` con `AI_PROVIDER=mock`, porque la cuenta de Anthropic no tiene crédito. En ese backend:

- las herramientas, Whisper, Kokoro, la base de datos (temporal) y el streaming son reales;
- solo la decisión del modelo es determinista.

En la app no se simula nada.

### FPS observados

Medidos con los paneles apartados («Ver núcleo»), 6 s por caso, en la app real.

| Calidad | Partículas | Con bloom | Sin bloom |
|---|---|---|---|
| LOW | 16.384 | 59,2 (en LOW el bloom «auto» se apaga) | 59,9 |
| MEDIUM | 65.536 | 57,3 | 60,0 |
| HIGH | 131.072 | 48,9 | 56,0 |

Con la cámara encendida, tras el arranque:

| Caso | Humanoide | Inferencia de manos |
|---|---|---|
| Auto (MEDIUM + bloom) | 49 FPS | 308 ms |
| MEDIUM sin bloom | 55,5 FPS | 228 ms |
| LOW | 57,4 FPS | 210 ms |
| HIGH sin bloom | 51,3 FPS | 272 ms |
| Sin figura (referencia) | — | ~330 ms |

En una corrida en frío, justo después de abrir la app, la inferencia llegó a ~990 ms con el humanoide; después se estabiliza. La calidad automática baja sola un nivel si los FPS se quedan por debajo de 42 durante 4 s; es el mismo monitor del núcleo anterior.

## 7. Problemas encontrados y corregidos

1. **EXECUTING no tenía una señal real.** El escritorio usaba el chat sin streaming.
   - Se pasó a `/chat/stream`, y el backend ahora emite `tool_done`.
   - EXECUTING dura exactamente lo que tarda la herramienta.
2. **El ruido de la sala animaba al humanoide en reposo** (manos libres con el micrófono abierto). El audio ahora solo lo mueve en `listening` y `speaking`.
3. **El pixel ratio quedaba fijo al crearse el motor.** Al cambiar de pantalla o de escala, la imagen se veía borrosa. `HumanoidCore` vigila `(resolution: Ndppx)` y actualiza el renderer, sin tocar el laboratorio.
4. **`data-state` no aparecía hasta el primer cambio de estado.** Ahora se pone `idle` al terminar la carga, igual que `Atlas3D`.
5. **Desborde de toda la interfaz en ventanas de menos de 1280 px.** Es un fallo anterior, no del humanoide.
   - Con el zoom estandarizado de Chromium 128+ (Electron 40), `width:121.95 %` ya no se compensa: la barra superior, el dock y la figura quedaban cortados por la derecha.
   - Ahora `width:100%`. `vh` sí se escala con el zoom, así que se mantiene compensado.
   - `min-height` se ajustó a los 635 px visibles de la ventana mínima.
6. **Fallos de entorno, no de código:**
   - **Bloqueo de login local (HTTP 429).** Un Electron de desarrollo viejo seguía intentando entrar con una contraseña anterior; se cerró.
   - **Arranque en frío de Kokoro (>90 s) en el backend de prueba.** Desaparece una vez cargado (síntesis en 1,0 s).
   - **Ventanas tapadas pausadas por Chromium durante las pruebas.** Se desactivó esa pausa en el banco de pruebas.

## 8. Limitaciones pendientes

- **El acceso directo `ATLAS.lnk` abre la instalación del 14-oct-2026**, que lleva su propio backend de esa fecha. Para ver el humanoide desde ese icono hay que regenerar el instalador (`npm run dist`) y reinstalar. Como el instalador empaqueta el backend de `bundle/`, que también está viejo, no se hizo sin consultar.
- **No se probó con IA real** (sin crédito de Anthropic) ni con **manos reales delante de la cámara**. La cámara se probó con vídeo simulado (la mano renderizada del GLB, el mismo método del laboratorio en la 5D).
- **Dos versiones de Three.js** en el paquete: r164 del humanoide y r180 del resto. Suman ~1,2 MB y muestran el aviso «Multiple instances of Three.js».
- **60 FPS sostenidos** se logran en LOW y en MEDIUM sin bloom en este equipo. Con bloom y la cámara encendida baja a ~49. El interruptor de bloom ya existe y no quita el núcleo del pecho.
- **Con los paneles abiertos el humanoide queda detrás del chat**, igual que el núcleo anterior. Se ve completo con «Ver núcleo».
- **Manos libres con la frase de corrido** («Atlas, ¿qué hora es?»): el motor de escucha pasa directo a transcribir y no se ve LISTENING. Es el comportamiento que ya tenía; con una pausa después de «Atlas» sí aparece.
- **Los efectos del núcleo anterior** (explosión, giro con las manos, «Probar pulso») no hacen nada con el humanoide.
- **Aprobar una acción pendiente** muestra EXECUTING durante toda la petición de confirmación. Esa ruta no tiene streaming.
- **Requiere WebGL2 y texturas flotantes.** Sin ellas aparece el núcleo anterior con el aviso en Configuración.

## 9. Cómo ejecutar

Desde `D:\Atlas\desktop\electron`:

```powershell
npm run build                                   # proceso principal + interfaz (incluye el humanoide y sus recursos)
Remove-Item Env:ELECTRON_RUN_AS_NODE -ErrorAction SilentlyContinue   # la terminal de VS Code lo define
npx electron .                                  # abre dist/ contra el backend de backend/.env
```

O, para desarrollo con recarga: `npm run dev`, que usa Vite en `:5173`. Ese puerto choca con el servicio «móvil» de `atlas.bat`, así que no conviene arrancar los dos a la vez.

Ajustes en *Configuración → Neural Core*:

- **Figura central:** humanoide de partículas o núcleo anterior.
- **Calidad gráfica:** automática, baja, media o alta.
- **Bloom.**
- **Reducir calidad si baja el rendimiento.**

Para depurar: abrir con `?neuralDebug` expone `window.__ATLAS_NEURAL_CORE__`. El humanoide está en `.humanoid.view` (`AtlasParticle3D`).

Banco de pruebas: `node D:\Atlas-e2e\humanoid\t1_smoke.mjs` y siguientes (de `t3` a `t11`). Para voz y herramientas, levantar antes el backend de prueba con `ATLAS_ENV_FILE=D:\Atlas-e2e\humanoid\backend_e2e.env` en `:8767`.
