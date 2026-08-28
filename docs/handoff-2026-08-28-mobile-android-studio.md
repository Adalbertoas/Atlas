# Handoff — probar la app móvil nativa (Flutter) en la PC con Android Studio

**Para la sesión de Claude que corra en la otra PC (la que tiene gráficas).**
Escrito el 28 ago 2026 desde la PC sin Android Studio, donde la app Flutter
se pudo escribir y analizar pero **no correr** (no hay emulador ni celular
conectado ahí).

## Objetivo de esta sesión

Instalar Android Studio, levantar un emulador (o conectar un celular por
USB) y **correr por primera vez `mobile_app/`** — la app nativa en Flutter,
que hasta ahora nunca se ejecutó en vivo. Confirmar que login, chat con
streaming y la lista de dispositivos funcionan de verdad contra el backend.

`mobile_app/` es distinto de `mobile/`: ese último es la PWA en HTML/CSS/JS
que ya funciona. La app Flutter es una exploración de un cliente nativo, no
un reemplazo — ver `mobile_app/README.md`.

## Estado al momento del handoff

- Rama `feature/mejoras-app-recordatorios-musica-clima`, commit `ef1cf8e`,
  todo pusheado a `origin`.
- `flutter analyze` → **sin issues**. Flutter 3.41.9 stable, Dart 3.11.5.
- Alcance implementado: **login, chat con streaming (`/api/v1/chat/stream`)
  y lista/control de dispositivos**. Nada más. Voz, push, Shazam, memoria y
  gestos siguen existiendo solo en la PWA `mobile/`.
- Nunca corrió en un dispositivo real ni en emulador. **Todo lo de abajo
  está sin confirmar en vivo.**

## BLOQUEO CONOCIDO: el backend corre en HTTPS y la app no lo va a aceptar

Esto casi seguro va a ser lo primero que falle, y no es obvio desde el
mensaje de error. Vale la pena resolverlo *antes* de perder tiempo
debuggeando el login.

`certs/dev-cert.pem` y `certs/dev-key.pem` existen, así que `backend/run.py`
levanta el servidor en **HTTPS con un certificado autofirmado**
(`backend/run.py:28-34`). En el navegador eso se resuelve entrando una vez
a mano y aceptando la advertencia — pero **Dart no tiene ese escape**:
`ApiClient` usa `package:http` pelado, sin `badCertificateCallback`
(`mobile_app/lib/services/api_client.dart`), así que cualquier request a
`https://` va a morir con `HandshakeException: CERTIFICATE_VERIFY_FAILED`.

Las dos salidas, en orden de preferencia:

1. **Correr el backend en HTTP plano para esta prueba** — renombrar
   temporalmente `certs/dev-cert.pem` y reiniciar `python run.py`. Es lo
   más rápido y no toca código. Ojo: la PWA `mobile/` necesita HTTPS para
   cámara/micrófono, así que si querés las dos cosas a la vez, esto no
   alcanza.
2. **Agregar un `HttpClient` con `badCertificateCallback` en `ApiClient`**,
   activado solo en debug (`kDebugMode`) y solo para el host de la LAN.
   Es la solución de fondo, pero es código nuevo — decidilo con el usuario
   antes de escribirlo, no lo asumas.

La app ya permite HTTP plano a propósito (`usesCleartextTraffic="true"` en
Android, `NSAllowsArbitraryLoads` en iOS), así que la opción 1 no necesita
ningún cambio del lado del cliente.

## Pasos

### 1. Traer el código

```powershell
cd <ruta>\Atlas
git checkout feature/mejoras-app-recordatorios-musica-clima
git pull
```

### 2. Instalar Android Studio y el SDK

Instalador oficial de Android Studio, y en el asistente de primer arranque
aceptar la instalación del **Android SDK** y del **Android Virtual Device**.
Después:

```powershell
cd mobile_app
flutter pub get
flutter doctor -v
```

Si `flutter doctor` marca `Could not determine java version`, es porque
está tomando un Java 8 viejo del PATH del sistema — apuntarlo al JDK que
trae Android Studio (ese es el problema que apareció en la otra PC):

```powershell
flutter config --jdk-dir="C:\Program Files\Android\Android Studio\jbr"
flutter doctor --android-licenses    # aceptar todo con "y"
```

`flutter doctor` tiene que quedar en verde en **Flutter** y en **Android
toolchain**. Lo de Visual Studio / "Desktop development with C++" no
importa acá — eso es solo para compilar apps de Windows, no de Android.

### 3. Levantar el backend

```powershell
cd backend
python run.py
```

Contraseña de login: `admin123`. Ver el bloqueo de HTTPS de más arriba
antes de este paso.

Anotar la **IP de LAN** de la PC (`ipconfig`) — hace falta para el paso 5.

### 4. Emulador o celular

```powershell
flutter devices          # tiene que aparecer el emulador o el celular
flutter run
```

El emulador se crea desde Android Studio (Device Manager → Create Device).
Con un celular físico hace falta activar **Opciones de desarrollador** y
**Depuración USB**, y aceptar el diálogo de confianza que aparece al
conectarlo.

### 5. La URL del servidor en el login

En la pantalla de login la URL está colapsada bajo **"Avanzado"** y hay que
escribirla a mano — no hay autodetección como en el navegador.

- **Emulador de Android**: `http://10.0.2.2:8000` — `10.0.2.2` es el alias
  del `localhost` de la PC anfitriona. `127.0.0.1` apunta al emulador
  mismo y no va a funcionar.
- **Celular físico en la misma WiFi**: la IP de LAN de la PC,
  ej. `http://192.168.1.50:8000`.

## Qué confirmar (nada de esto está probado en vivo todavía)

- [ ] La app compila y arranca en el emulador/celular.
- [ ] Login con `admin123` guarda el token (cerrar y reabrir la app tiene
      que entrar directo al home, sin volver a pedir la contraseña).
- [ ] Chat: la respuesta **aparece token por token**, no de golpe al final
      (eso es lo que prueba que el parseo de SSE a mano funciona).
- [ ] La lista de dispositivos carga desde `/api/v1/devices`.
- [ ] El toggle de un dispositivo lo prende/apaga de verdad. Recordar que
      no hay API de control directa: manda un comando en lenguaje natural
      por `/api/v1/chat` ("encendé `<nombre>`"), igual que el dashboard y
      la PWA — así que pasa por el Orchestrator y el Permission Manager, y
      puede pedir confirmación.
- [ ] Sesión expirada: hacer `/auth/logout` desde otro cliente y confirmar
      que el próximo request de la app cae al login en vez de romperse.

## Después de probar

Anotar el resultado en `docs/pending-manual-tests.md` (esa es la
convención del repo), commitear y pushear para que la otra PC lo vea.

Si la app funciona, lo siguiente que falta es todo lo que la PWA ya tiene y
la nativa no: voz (STT/TTS), notificaciones push, Shazam, memoria,
automatizaciones y control por gestos. **No empezar nada de eso sin
confirmarlo con el usuario** — la idea era ver primero si el camino nativo
vale la pena.

## Sobre iOS

No se puede compilar ni probar desde Windows: hace falta Xcode, que solo
corre en macOS. El código es compatible (`Info.plist` ya está ajustado)
pero está **sin verificar**. No prometer que funciona.
