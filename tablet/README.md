# ATLAS para tablet (Flutter, Android)

Cliente de ATLAS pensado para tablet. No tiene IA propia: habla con el backend que
corre en la PC (`backend/`, puerto 8000), igual que el cliente de escritorio.

## Qué hace

- **Chat**: escribir, dictar por voz (toque para empezar, toque para enviar) y
  adjuntar fotos con la cámara, imágenes de la galería o PDF. Los archivos que
  genera ATLAS (por ejemplo, el Excel de una factura) aparecen con botones
  **Descargar** (elegís dónde guardarlo), **Abrir** y **Compartir**.
- **Hoy**: hora, clima, recordatorios, avisos y titulares. En horizontal se ve
  al lado del chat.
- **Casa**: dispositivos por habitación; al tocar uno se lo pide a ATLAS por el
  chat, así pasa por las mismas confirmaciones de seguridad.
- **Memoria** y **Ajustes** (conexión, voz).

## Compilar e instalar

```powershell
powershell -ExecutionPolicy Bypass -File tablet\build_apk.ps1
```

Compila `build\app\outputs\flutter-apk\app-release.apk` y, si hay una tablet
conectada por USB con depuración activada, la instala. Las cachés de Gradle y
Dart quedan en `D:\dev-cache` (C: está casi lleno).

## Conexión con la PC

La primera vez la app pide la dirección del backend y la contraseña de ATLAS
(si `AUTH_ENABLED=true`).

- **Por WiFi**: `https://<IP de la PC>:8000`. La tablet y la PC tienen que verse
  en la red y el Firewall de Windows tiene que permitir el puerto 8000.
- **Por cable USB** (sin red compartida): `adb reverse tcp:8000 tcp:8000` y en la
  app `https://127.0.0.1:8000`. Hay que repetir el `adb reverse` cada vez que se
  reconecta el cable.

El backend usa un certificado autofirmado (`certs/dev-cert.pem`). La app muestra
su huella SHA-256 la primera vez y después solo acepta ese certificado; si se
regenera, hay que desconectar la tablet en Ajustes y volver a conectarla.

## Desarrollo

```powershell
$env:PUB_CACHE = "D:\dev-cache\pub"; $env:GRADLE_USER_HOME = "D:\dev-cache\gradle"
cd tablet
flutter analyze
flutter test
flutter run          # con la tablet conectada
```
