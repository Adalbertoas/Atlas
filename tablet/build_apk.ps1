# Compila el APK de ATLAS para la tablet y, si hay una tablet conectada por USB, lo instala.
#   powershell -ExecutionPolicy Bypass -File tablet\build_apk.ps1            # compilar e instalar
#   powershell -ExecutionPolicy Bypass -File tablet\build_apk.ps1 -NoInstall
#
# Las cachés de Gradle y de Dart van a D:\dev-cache porque C: está casi lleno.
param([switch]$NoInstall)

$ErrorActionPreference = "Stop"
$env:PUB_CACHE = "D:\dev-cache\pub"
$env:GRADLE_USER_HOME = "D:\dev-cache\gradle"
Set-Location $PSScriptRoot

flutter pub get
flutter build apk --release --target-platform android-arm64
if ($LASTEXITCODE -ne 0) { throw "La compilación falló." }

$apk = Join-Path $PSScriptRoot "build\app\outputs\flutter-apk\app-release.apk"
Write-Host "APK: $apk"

if (-not $NoInstall) {
    $adb = Join-Path $env:LOCALAPPDATA "Android\Sdk\platform-tools\adb.exe"
    $devices = & $adb devices | Select-String "\tdevice$"
    if ($devices) {
        & $adb install -r $apk
        # Sin WiFi compartida: el puerto 8000 de la tablet llega a la PC por el cable.
        & $adb reverse tcp:8000 tcp:8000
        Write-Host "Instalado. Por USB, conectá la app a https://127.0.0.1:8000"
    } else {
        Write-Host "No hay tablet conectada por USB: copiá el APK a la tablet e instalalo desde ahí."
    }
}
