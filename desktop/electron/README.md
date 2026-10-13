# ATLAS Holographic Desktop

Nueva aplicación de escritorio independiente basada en Electron, React, TypeScript y React Three Fiber. El cliente `desktop/atlas_desktop` continúa disponible y no fue reemplazado.

## Ejecutar en desarrollo

1. Instalá Node.js LTS (incluye npm).
2. Desde esta carpeta, ejecutá:

```powershell
npm install
npm run dev
```

## Arquitectura

- `electron/main.ts`: proceso principal, ventana nativa y servicios Windows.
- `electron/preload.cts`: puente IPC limitado y aislado.
- `src/three/Hologram.tsx`: humanoide holográfico 3D procedural de partículas; admite una futura sustitución por GLB.
- `src/components/FloatingPanel.tsx`: paneles flotantes movibles, redimensionables, minimizables y cerrables.
- `src/main.tsx`: navegación, conversación, paneles, estado visual y módulos.
- `src/atlas/`: **Neural Core**, el núcleo de partículas 3D con control por gestos y reacción a la voz. Ver [`docs/ATLAS_NEURAL_CORE.md`](../../docs/ATLAS_NEURAL_CORE.md).

## Pruebas

```powershell
npm test          # pruebas unitarias (runner nativo de Node)
npm run typecheck
```

El renderer mantiene `contextIsolation`, `sandbox` y `nodeIntegration: false`. Las operaciones de sistema usan una lista explícita de canales IPC. CPU, memoria, discos, GPU y procesos se recogen desde el proceso principal; cuando Windows no expone una métrica, la interfaz indica que no está disponible.