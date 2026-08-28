"""Smoke test E2E del dashboard: navegador real (Chromium vía Playwright)
contra un backend real (AI_PROVIDER=mock, sin gastar nada) — la primera
cobertura automatizada de este proyecto que ejercita el frontend en un
navegador, no solo la API. No reemplaza los tests del backend (que cubren
la lógica en profundidad); esto cubre lo que solo se rompe en el navegador:
JS con errores de sintaxis, IDs de HTML que dejaron de coincidir con
app.js, CSS que esconde un elemento que debería verse.

Cómo correrlo (aparte de backend/tests — ver conftest.py del porqué):
    cd backend && .venv\\Scripts\\Activate.ps1
    pip install -r ../dashboard/tests_e2e/requirements.txt
    playwright install chromium   # una sola vez, ~150MB
    pytest ../dashboard/tests_e2e -v
"""
from __future__ import annotations

import re

from playwright.sync_api import Page, expect

# Mismo valor que conftest.py — duplicado a propósito en vez de importado:
# depender de `from conftest import ...` acopla el import de este archivo al
# modo en que pytest resuelve rootdir/sys.path, que puede variar según desde
# dónde se invoque `pytest`.
ATLAS_PASSWORD = "e2e-test-password"


def _login(page: Page, dashboard_url: str, backend_url: str, password: str = ATLAS_PASSWORD) -> None:
    page.goto(dashboard_url)
    # La URL del backend no se autodetecta en el test: detectApiUrl() prueba
    # el puerto 8000 fijo (el de un `python run.py` normal), pero acá el
    # backend real levantó en un puerto dinámico — se lo pasa a mano por el
    # mismo campo que usaría cualquiera con el backend en otra máquina/puerto.
    # Vive colapsado dentro de <details id="advanced-details"> ("Avanzado"),
    # hay que abrirlo antes de que el campo sea visible/editable.
    page.click("#advanced-details summary")
    page.fill("#login-api-url", backend_url)
    page.fill("#login-password", password)
    page.click("#login-form button[type=submit]")


def test_login_with_wrong_password_shows_error(page: Page, dashboard_url: str, backend_url: str):
    _login(page, dashboard_url, backend_url, password="incorrecta")

    expect(page.locator("#login-error")).to_contain_text("incorrecta")
    expect(page.locator("#app-screen")).to_be_hidden()


def test_login_succeeds_and_shows_the_home_view(page: Page, dashboard_url: str, backend_url: str):
    _login(page, dashboard_url, backend_url)

    expect(page.locator("#app-screen")).to_be_visible()
    expect(page.locator("#login-screen")).to_be_hidden()


def test_chat_smoke_sends_and_receives_a_reply(page: Page, dashboard_url: str, backend_url: str):
    """Ejercita el endpoint de streaming (dashboard/app.js -> /chat/stream)
    de punta a punta en un navegador real — hasta ahora solo estaba probado
    vía TestClient (que no ejecuta el JS) o curl (que no arma el DOM)."""
    _login(page, dashboard_url, backend_url)

    page.click('.nav-button[data-view="chat"]')
    page.fill("#chat-input", "¿qué hora es?")
    page.click('#chat-form button[type=submit]')

    # MockProvider responde con la tool get_current_time — el texto exacto
    # no importa (depende de la hora), alcanza con que llegue *alguna*
    # respuesta de ATLAS después del mensaje del usuario.
    atlas_bubble = page.locator(".chat-bubble.atlas").last
    expect(atlas_bubble).to_be_visible(timeout=10_000)
    expect(atlas_bubble).not_to_have_class(re.compile(r"\btyping\b"))
    expect(atlas_bubble).not_to_be_empty()


def test_devices_view_shows_mock_devices(page: Page, dashboard_url: str, backend_url: str):
    _login(page, dashboard_url, backend_url)

    page.click('.nav-button[data-view="devices"]')

    # "Luz Sala" es uno de los 4 dispositivos fijos de MockSmartHomeProvider
    # (app/smart_home/mock_provider.py) — sin hardware real de por medio.
    expect(page.locator("#view-devices")).to_contain_text("Luz Sala", timeout=10_000)


def test_logout_returns_to_login_screen(page: Page, dashboard_url: str, backend_url: str):
    _login(page, dashboard_url, backend_url)
    expect(page.locator("#app-screen")).to_be_visible()

    page.click("#logout-button")

    expect(page.locator("#login-screen")).to_be_visible()
    expect(page.locator("#app-screen")).to_be_hidden()
