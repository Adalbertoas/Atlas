# ATLAS Mobile (nativo)

App nativa en Flutter (Android + iOS desde un solo código) — distinta de
`mobile/`, que es la PWA existente (HTML/CSS/JS vanilla). Las dos conviven:
esta es la exploración de un cliente nativo, no un reemplazo todavía.

**Alcance actual:** login, chat (con streaming en vivo contra
`/api/v1/chat/stream` y Markdown renderizado), dispositivos, rutinas,
notificaciones y memoria. Lo que necesita hardware o permisos del celular
—voz, cámara, push, Shazam, gestos— sigue existiendo solo en la PWA; ver
"Qué falta" más abajo.

La interfaz sigue el diseño del dashboard (`dashboard/styles.css`), no el de
la PWA `mobile/`, que quedó con la paleta anterior al rediseño: misma
paleta, mismas fuentes (Inter + Space Grotesk, empaquetadas), mismas
tarjetas y la misma barra con marca, estado de conexión y título de vista.

## Importante: iOS no se puede compilar ni probar en Windows

El código es compatible con iOS (Flutter compila un solo código para ambas
plataformas — `NSAppTransportSecurity` en `ios/Runner/Info.plist` ya está
ajustado, igual que su equivalente Android), pero **compilar, correr o
probar la mitad de iOS requiere Xcode, que solo corre en macOS**. En este
entorno (Windows) solo se pudo compilar y verificar Android. Cuando haya
acceso a un Mac (propio o un servicio de CI como Codemagic/GitHub Actions
con runner macOS), el mismo código debería compilar para iOS sin cambios
grandes — pero no está verificado.

## Requisitos

- Flutter SDK (`flutter --version` — probado con 3.41.9).
- Android SDK con `platforms;android-36` y `build-tools;28.0.3` además de
  las versiones que ya traiga (`flutter doctor` avisa si falta algo).
- Un JDK 17+ (`JAVA_HOME` apuntando ahí) — Java 8 no alcanza.
- El backend de ATLAS corriendo y alcanzable desde el dispositivo/emulador
  (misma IP de LAN que usan `dashboard/` y `mobile/`).

## Correrla

```powershell
cd mobile_app
flutter pub get
flutter run                 # con un emulador o celular conectado (USB debugging)
# o, para solo verificar que compila sin correrla:
flutter build apk --debug
```

En el login, la URL del servidor está colapsada bajo "Avanzado" (mismo
patrón que `dashboard/index.html`) — hace falta escribirla a mano
(ej. `http://192.168.1.50:8000`), no hay forma de autodetectarla como
`location.hostname` en un navegador.

**HTTP plano permitido a propósito** (`android:usesCleartextTraffic="true"`,
`NSAllowsArbitraryLoads` en iOS): el backend en LAN muchas veces corre sin
el certificado autofirmado de `scripts/generate_dev_cert.py`. Mismo
criterio que el resto de los clientes — pensado para una red de confianza,
no para exponerlo a internet.

## Arquitectura

```
lib/
├── main.dart              # entry point, decide login vs. home según haya token guardado
├── models/                # espejos de los schemas del backend
│   ├── chat_message.dart  # texto mutable — se llena token a token con el streaming
│   ├── device.dart        # DeviceOut (backend/app/smart_home/schemas.py)
│   ├── routine.dart       # RoutineOut + RoutineRunResult
│   ├── notification_item.dart
│   └── memory_entry.dart
├── services/
│   └── api_client.dart    # login/logout, /chat, /chat/stream (SSE a mano) y las listas
├── theme/
│   └── atlas_theme.dart   # paleta, radios y fuentes de dashboard/styles.css
├── utils/
│   └── format.dart
├── widgets/
│   ├── atlas_chrome.dart  # marca, punto de estado, tarjetas y lista de recursos
│   └── markdown_text.dart # el equivalente Dart de shared/markdown.js
└── screens/
    ├── login_screen.dart
    ├── home_screen.dart   # shell con barra superior y 5 pestañas
    ├── chat_screen.dart
    ├── devices_screen.dart
    ├── automations_screen.dart
    ├── notifications_screen.dart
    └── memory_screen.dart
```

**Decisiones que vale la pena no perder:**

- **Sin gestor de estado externo** (`provider`, `riverpod`, etc.): con 6
  pantallas y un solo `ApiClient` compartido por constructor, alcanza con
  `StatefulWidget` + `setState`. Mismo espíritu que dashboard/mobile
  (JS vanilla, sin framework) — se suma una dependencia de estado si el
  alcance crece lo suficiente como para justificarla.
- **El streaming de chat se parsea a mano** (`ApiClient.sendChatStream`),
  replicando el mismo protocolo que ya consume `dashboard/app.js`
  (`event: <tipo>\ndata: <json>\n\n`) — no hay paquete de Dart para SSE en
  el catálogo estándar que valga la pena traer para esto.
- **Los dispositivos no tienen una API de control directa**: no existe
  (`GET /api/v1/devices` es de solo lectura — ver
  `backend/app/api/v1/devices.py`). El toggle manda un comando en lenguaje
  natural por `/api/v1/chat` ("encendé/apagá `<nombre>`"), igual que
  `dashboard/app.js` y `mobile/app.js` — todo pasa por el Orchestrator y el
  Permission Manager, ni el celular tiene un atajo directo.
- **Las fuentes van empaquetadas** (`assets/fonts/`), no traídas del CDN de
  Google como en `dashboard/index.html`: la app corre contra un backend de
  la LAN y tiene que verse igual sin internet.
- **El Markdown se renderiza a mano** (`widgets/markdown_text.dart`), igual
  que `shared/markdown.js` lo hace para el dashboard y la PWA: un paquete de
  pub.dev traería un parser CommonMark entero para lo que el modelo
  realmente usa (negritas, listas, código, links). Diferencia conocida: los
  links de YouTube no muestran la tarjeta con miniatura que sí arma la web.
- **Las cuatro listas comparten `AtlasResourceList`**: los cuatro estados
  (cargando, error, vacía, con datos) y el "deslizar para actualizar" se
  escriben una sola vez, para que no terminen mostrando el error de maneras
  distintas.
- **Sesión expirada/revocada**: cualquier 401 (token vencido, o revocado
  desde otro dispositivo con `/auth/logout`) limpia el token local y manda
  de vuelta al login (`ApiClient.onSessionExpired`) — mismo criterio que el
  helper `api()` de dashboard/app.js.

## Qué falta (fuera de alcance de esta primera versión)

Todo lo que necesita hardware o permisos del celular y hoy solo existe en
`mobile/`: voz (STT/TTS y wake word), notificaciones push, la foto para
visión, Shazam y el control por gestos. También falta crear rutinas y
memorias desde la app — hoy se leen y se ejecutan/olvidan, pero darlas de
alta se hace por chat, igual que en el dashboard.
