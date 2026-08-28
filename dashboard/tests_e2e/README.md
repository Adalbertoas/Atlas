# Smoke test E2E del dashboard

Primera cobertura automatizada que abre un navegador real (Chromium, vía
Playwright) contra un backend real — hasta ahora los ~300 tests de
`backend/tests/` prueban la API a fondo, pero nunca ejecutan el JavaScript
del dashboard. Esto no los reemplaza: cubre lo que solo se rompe en el
navegador (un ID de HTML que dejó de coincidir con `app.js`, un error de
sintaxis en el JS, CSS que esconde algo que debería verse).

## Requisitos

Un venv de Python con `backend/requirements.txt` ya instalado (reutiliza
`app.main` directo, sin subir un proceso aparte — ver `conftest.py`), más:

```powershell
cd backend
.venv\Scripts\Activate.ps1
pip install -r ..\dashboard\tests_e2e\requirements.txt
playwright install chromium   # una sola vez, ~150MB
```

## Correrlo

```powershell
# Desde backend/, con el venv activado:
pytest ..\dashboard\tests_e2e -v
```

**No mezclar con `pytest` de `backend/tests/`** en la misma invocación: cada
suite fija sus propias variables de entorno (`DATABASE_URL`, `AI_PROVIDER`,
etc.) al importar su `conftest.py`, y esas variables solo se leen la primera
vez que se importa `app.config`/`app.core.database` en el proceso — correr
ambas juntas haría que una pise la configuración de la otra. Son dos
invocaciones de `pytest` separadas a propósito.

## Qué cubre

- Login (contraseña incorrecta muestra error; correcta entra a Inicio).
- Chat de punta a punta contra el endpoint de streaming
  (`/api/v1/chat/stream`) — el primer test que lo ejercita en un navegador
  real, no solo vía `TestClient` o `curl`.
- Vista de Dispositivos con los 4 dispositivos fijos de
  `MockSmartHomeProvider` (sin hardware real).
- Logout (vuelve a la pantalla de login).

## Qué no cubre (fuera de alcance de un smoke test)

Voz, gestos, notificaciones push, Shazam — todo lo que depende de
permisos del navegador (micrófono/cámara) no es práctico de automatizar acá
sin mockear `getUserMedia`, y el valor de hacerlo no compensa la
complejidad para un smoke test. `mobile/` y `desktop/` tampoco están
cubiertos todavía — mismo patrón, para cuando haga falta.
