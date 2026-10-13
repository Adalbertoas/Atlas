# Plan de integración — ATLAS Neural Particle Core

Fecha: 2026-10-13. Alcance: `desktop/electron` (cliente Electron + React + Three.js).
No se toca el backend, el dashboard, la PWA móvil, Blender ni `integrations/`.

## Resultado de la auditoría

| Punto | Hallazgo |
|---|---|
| Frontend | Electron 40, React 19.3, Vite 7, TypeScript 5 (`desktop/electron`). |
| Three.js | `three@0.180` y `@react-three/fiber@9.8` instalados. `src/three/Hologram.tsx` existe pero no está montado. |
| Visual central | Fondo CSS `.space-backdrop` (planeta, órbitas) y `VoiceOrb` CSS dentro del chat. |
| Voz | Inexistente en Electron: el micrófono es un aviso y `speaking` es un temporizador de 950 ms. El backend expone `POST /api/v1/voice/transcribe` y `POST /api/v1/voice/speak` (WAV); el dashboard ya los usa con `AnalyserNode`. |
| Estados | No hay máquina de estados en el renderer. El `EventBus` del backend no llega al cliente. |
| IA | `atlas:chat` por IPC → `POST /api/v1/chat` (sin streaming en Electron). |
| MCP | ATLAS no tiene configuración MCP propia; no se modifica nada. |
| Permisos | Electron no define `setPermissionRequestHandler` (concede todo por defecto). |
| Tests | Sin runner en `desktop/electron`. Node 24 ejecuta `.ts` de forma nativa. |
| GPU local | Intel UHD 630 (integrada). |

## Decisiones

1. **Motor en Three.js puro**, no R3F: el núcleo no depende de React ni del asistente.
2. **Una dependencia nueva**: `@mediapipe/tasks-vision` (Hand Landmarker oficial). WASM y
   modelo se sirven desde `public/mediapipe/` (local, sin CDN en tiempo de ejecución).
3. **Tests con `node --test`** (Node 24 ejecuta TypeScript): cero dependencias de test.
   La lógica pura (gestos, estados, audio, calidad) vive en módulos sin DOM ni Three.js.
4. **Voz real en Electron**: dos canales IPC nuevos que reenvían a los endpoints que ya
   existen. Una sola captura de micrófono alimenta grabación y análisis.
5. **Estados conectados solo a eventos reales** mediante un adaptador; nada simulado.
6. **Cámara apagada por defecto y nunca persistida**: se activa por sesión con consentimiento.

## Archivos nuevos (`desktop/electron/`)

```
src/atlas/
  particle-core/   ParticlePresets, ParticleData, ParticleGeometry, ParticleShaders,
                   ParticleMaterial, ParticleAnimator, ParticleEffects, PerformanceMonitor,
                   ParticleCore
  hand-tracking/   types, GestureConfig, LandmarkSmoother, handFeatures,
                   GestureStateMachine, GestureRecognizer, GestureController,
                   HandTrackingService
  audio-reactive/  audioFeatures, VoiceVisualizer, AudioAnalyzer
  voice/           VoiceSession
  interaction/     AtlasVisualStateMachine, InteractionConfig, AtlasInteractionController
  ui/              ParticleCoreView, NeuralCoreSettings, CameraPermissionControl,
                   NeuralCoreHud, HandDebugOverlay, useNeuralCore, neural-core.css
  **/*.test.ts     pruebas unitarias
src/components/Controls.tsx      (Toggle/Range extraídos de main.tsx + Select)
scripts/setup-mediapipe.mjs      (copia WASM desde node_modules y descarga el modelo)
docs/ATLAS_NEURAL_CORE.md        (documentación final)
```

## Archivos modificados

| Archivo | Cambio |
|---|---|
| `src/main.tsx` | Monta el núcleo y el HUD, añade la sección **Neural Core** a Configuración, conecta el micrófono y sustituye el temporizador `speaking` por estados reales. |
| `electron/main.ts` | Canales `atlas:transcribe` y `atlas:speak`; `setPermissionRequestHandler` que solo concede cámara/micrófono a la propia ventana. |
| `package.json` | Dependencia MediaPipe; scripts `test`, `typecheck`, `setup:mediapipe`. |
| `README.md` (electron) | Referencia a la nueva documentación. |

## Flujo de datos

```
Cámara → HandTrackingService → LandmarkSmoother → GestureRecognizer
       → GestureStateMachine → GestureController ─┐
Micrófono / audio TTS → AudioAnalyzer → VoiceVisualizer ─┤
Eventos reales (chat, voz) → AtlasVisualStateMachine ────┤
                                                         ▼
                            AtlasInteractionController → ParticleCore (GPU)
```

## Orden de trabajo

1. Núcleo de partículas y shaders. 2. Vista e integración en la UI. 3. MediaPipe y motor de
gestos. 4. Audio y voz. 5. Estados. 6. Configuración. 7. Optimización. 8. Pruebas y documentación.

Sin despliegues, sin `push`, sin releases.
