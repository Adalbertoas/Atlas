# Integración de Gods Eye View

ATLAS incorpora una vista **Mundo en vivo** en el dashboard para mostrar la consola geoespacial local de [Gods Eye View](https://github.com/bilawalsidhu/gods-eye-view).

## Inicio

El código se mantiene como submódulo en `integrations/gods-eye-view` para conservar su historial y licencia MIT.

```powershell
git submodule update --init --recursive
cd integrations/gods-eye-view
npm ci
npm run dev
```

Antes de `npm run dev`, creá `integrations/gods-eye-view/.env` (git lo ignora) con:

```ini
HOST=127.0.0.1
PORT=4173
GEV_EMBED_FRAME_ANCESTORS=http://127.0.0.1:5174 http://localhost:5174
```

Sin `HOST`, Vite escucha solo en `localhost` (IPv6) y el dashboard no lo encuentra. Sin `GEV_EMBED_FRAME_ANCESTORS`, Gods Eye View rechaza ser embebido y el panel queda en blanco.

Gods Eye View debe quedar disponible en `http://127.0.0.1:4173`. Luego abrí **Mundo** en el dashboard de ATLAS y elegí **Recargar**. El panel detecta el servicio y lo muestra embebido; **Abrir aparte** abre la consola en una pestaña independiente.

## ATLAS maneja el globo

Con el servicio corriendo, ATLAS puede consultar y mover el globo por chat o por voz:

- "¿Qué vuelos hay sobre Buenos Aires?" — `query_world` (solo lectura): aviones, aviones militares, barcos, terremotos, incendios, satélites, ciclones, lanzamientos, cámaras públicas o un resumen de situación de una zona.
- "Mostrame Tokio en el mapa" — `show_world_view` (riesgo bajo, sin confirmación): lleva el globo a un lugar o coordenadas, con capas y estilo visual opcionales.
- "Seguí la ISS" / "seguí el vuelo ARG1676" — `show_world_view` con la cámara pegada a un satélite o a un avión en vuelo.
- "Marcame la ruta de Buenos Aires a Córdoba, Argentina" — `show_world_view` con marcas: pines, etiquetas, áreas, flechas y rutas. Las rutas son líneas rectas entre lugares, no caminos. Si un nombre es ambiguo conviene decir el país: "Córdoba" a secas cae en España.
- "¿Qué clima hace en Lima?", "mostrame la imagen satelital" — `query_world` con `weather`, `satellite_image` (nubes, mundial), `radar_image` (lluvia, solo EE. UU.) o `camera_image`. Las imágenes aparecen en el chat.
- "Avisame si hay un terremoto mayor a 5 cerca de Chile", "avisame cuando pase la ISS sobre casa" — `create_world_alert`. El backend revisa cada alerta cada pocos minutos y deja una notificación cuando aparece algo nuevo; la primera revisión solo toma nota de lo que ya había. Se listan y borran desde **Mundo → Alertas activas**.

Cómo viaja el pedido:

1. La tool llama por HTTP al servidor MCP de Gods Eye View (`GODS_EYE_URL/mcp`, en `backend/.env`; por defecto `http://127.0.0.1:4173`). Ese endpoint solo acepta pedidos de esta misma máquina.
2. Cada respuesta trae la vista que la ilustra. El backend guarda la última y la expone en `GET /api/v1/world/view`.
3. El dashboard sondea ese endpoint, abre **Mundo** y le pasa la vista al iframe con el mensaje `gev:view`. Como es un sondeo, también reacciona a pedidos hechos desde el cliente de escritorio o el móvil.

`GODS_EYE_URL` vacío quita ambas herramientas. Con `AI_PROVIDER=mock` solo responden a frases con palabras clave (vuelos, aviones, barcos, terremotos, satélites, incendios, ciclones, lanzamientos, o "mostrame X en el mapa").

El nombre del lugar que pidas sale de tu PC: Gods Eye View lo resuelve con un geocodificador público y consulta los proveedores de cada capa. Algunos temas necesitan clave propia en `integrations/gods-eye-view/.env` (barcos: `AISSTREAM_API_KEY`); sin ella, ATLAS devuelve el error del proveedor.

## Requisitos y datos

- Gods Eye View exige Node.js 24.14+ o 26.x.
- Funciona sin claves con capas públicas básicas. Las opciones 3D avanzadas y algunos proveedores requieren credenciales propias, configuradas únicamente dentro de `integrations/gods-eye-view/.env` y nunca en ATLAS.
- Los datos pueden retrasarse, ser incompletos o inexactos. No usar la vista para navegación, emergencias ni decisiones críticas.
- El código de Gods Eye View está bajo MIT; sus datasets y proveedores conservan sus propios términos.