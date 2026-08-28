# ATLAS Mobile (nativo)

App nativa en Flutter (Android + iOS desde un solo código) — distinta de
`mobile/`, que es la PWA existente (HTML/CSS/JS vanilla). Las dos conviven:
esta es la exploración de un cliente nativo, no un reemplazo todavía.

**Alcance de esta primera versión:** login, chat (con streaming en vivo
contra `/api/v1/chat/stream`) y lista/control de dispositivos. El resto de
lo que ya tiene la PWA (voz, gestos, notificaciones push, Shazam, memoria)
queda para iteraciones siguientes — ver "Qué falta" más abajo.

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
├── models/
│   ├── chat_message.dart  # texto mutable — se llena token a token con el streaming
│   └── device.dart        # espejo de DeviceOut (backend/app/smart_home/schemas.py)
├── services/
│   └── api_client.dart    # login/logout, /chat, /chat/stream (SSE a mano), /devices
├── theme/
│   └── atlas_theme.dart   # misma paleta que dashboard/styles.css
└── screens/
    ├── login_screen.dart
    ├── home_screen.dart   # shell con navegación inferior
    ├── chat_screen.dart
    └── devices_screen.dart
```

**Decisiones que vale la pena no perder:**

- **Sin gestor de estado externo** (`provider`, `riverpod`, etc.): con 4
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
- **Sesión expirada/revocada**: cualquier 401 (token vencido, o revocado
  desde otro dispositivo con `/auth/logout`) limpia el token local y manda
  de vuelta al login (`ApiClient.onSessionExpired`) — mismo criterio que el
  helper `api()` de dashboard/app.js.

## Qué falta (fuera de alcance de esta primera versión)

Voz (STT/TTS), notificaciones push, Shazam, memoria, automatizaciones,
control por gestos — todo lo que ya tiene `mobile/` salvo chat y
dispositivos. Se suma en iteraciones siguientes si esta primera versión
resulta el camino a seguir.
