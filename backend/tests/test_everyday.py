"""Clima, noticias, divisas, calculadora, contraseñas, personalidad ampliada y migración de columnas."""
from __future__ import annotations

import string
from datetime import datetime

import pytest
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.pool import StaticPool

from app.everyday import calculator, currency, news, weather
from app.personality.schemas import PersonalityUpdate
from app.personality.service import build_system_prompt, describe_now, get_profile, update_profile
from app.tools.base import ToolContext
from app.tools.everyday import everyday_tools as tools
from app.tools.registry import tool_registry
from app.web.client import WebError

# ---------- calculadora ----------


@pytest.mark.parametrize(
    ("expression", "expected"),
    [
        ("2+2", 4),
        ("(1500*1.18)/12", 147.5),
        ("2^10", 1024),
        ("sqrt(81)", 9),
        ("15% de 200", 30),
        ("10 ÷ 4", 2.5),
        ("-3 * 3", -9),
        ("round(pi, 2)", 3.14),
    ],
)
def test_calculator_evaluates(expression, expected):
    assert calculator.calculate(expression) == pytest.approx(expected)


@pytest.mark.parametrize(
    "expression",
    ["__import__('os')", "open('x')", "9**9**9", "1/0", "factorial(10000)", "a + 1", "", "2 +"],
)
def test_calculator_rejects_unsafe_or_invalid(expression):
    with pytest.raises(calculator.CalculatorError):
        calculator.calculate(expression)


def test_calculate_tool_reports_errors_without_raising(db_session):
    context = ToolContext(db=db_session)
    assert tools.CalculateTool().execute({"expression": "6*7"}, context).data.endswith("= 42")
    result = tools.CalculateTool().execute({"expression": "1/0"}, context)
    assert not result.success and "cero" in result.error


# ---------- contraseñas ----------


def test_generate_password_respects_length_and_groups(db_session):
    context = ToolContext(db=db_session)
    password = tools.GeneratePasswordTool().execute({"length": 32}, context).data
    assert len(password) == 32
    assert any(c in string.ascii_lowercase for c in password)
    assert any(c in string.ascii_uppercase for c in password)
    assert any(c in string.digits for c in password)

    plain = tools.GeneratePasswordTool().execute({"length": 4, "symbols": False}, context).data
    assert len(plain) == 8  # mínimo
    assert plain.isalnum()


# ---------- abrir sitios ----------


def test_open_website_only_opens_web_addresses(db_session, monkeypatch):
    opened = []
    monkeypatch.setattr(tools.webbrowser, "open", opened.append)
    context = ToolContext(db=db_session)

    assert tools.OpenWebsiteTool().execute({"url": "youtube.com"}, context).success
    assert opened == ["https://youtube.com"]
    assert not tools.OpenWebsiteTool().execute({"url": "file:///C:/Windows/system32"}, context).success
    assert not tools.OpenWebsiteTool().execute({"url": "javascript:alert(1)"}, context).success
    assert len(opened) == 1


# ---------- clima ----------

GEOCODE = {
    "results": [
        {"name": "Santo Domingo", "admin1": "Santo Domingo", "country": "Ecuador", "country_code": "EC",
         "latitude": -0.25, "longitude": -79.17},
        {"name": "Santo Domingo", "admin1": "Distrito Nacional", "country": "República Dominicana",
         "country_code": "DO", "latitude": 18.47, "longitude": -69.89},
    ]
}  # fmt: skip
FORECAST = {
    "current": {"temperature_2m": 29.4, "apparent_temperature": 33.1, "relative_humidity_2m": 74,
                "weather_code": 2, "wind_speed_10m": 14.0, "is_day": 1},
    "daily": {"time": ["2026-11-17", "2026-11-18", "2026-11-19"], "weather_code": [2, 61, 95],
              "temperature_2m_max": [31, 30, 29], "temperature_2m_min": [23, 23, 22],
              "precipitation_probability_max": [10, 70, 90]},
}  # fmt: skip


def _fake_get_json(url, params=None):
    return GEOCODE if "geocoding" in url else FORECAST


def test_weather_prefers_the_country_after_the_comma(monkeypatch):
    monkeypatch.setattr(weather, "get_json", _fake_get_json)
    result = weather.get_weather("Santo Domingo, República Dominicana", days=3)
    assert "República Dominicana" in result.place
    assert result.description == "parcialmente nublado"
    assert [d.day_name for d in result.days] == ["hoy", "mañana", "jueves"]
    assert result.days[2].icon == "storm"
    assert "29 °C" in result.summary()


def test_weather_tool_uses_profile_city_and_explains_missing_city(db_session, monkeypatch):
    monkeypatch.setattr(weather, "get_json", _fake_get_json)
    monkeypatch.setattr(tools, "get_settings", lambda: type("S", (), {"home_place": ""})())
    context = ToolContext(db=db_session)

    missing = tools.GetWeatherTool().execute({}, context)
    assert not missing.success and "ciudad" in missing.error

    update_profile(db_session, PersonalityUpdate(home_city="Santo Domingo, República Dominicana"))
    assert "República Dominicana" in tools.GetWeatherTool().execute({}, context).data


def test_weather_unknown_place(monkeypatch):
    monkeypatch.setattr(weather, "get_json", lambda url, params=None: {})
    with pytest.raises(WebError):
        weather.geocode("Lugar Inexistente")


# ---------- noticias ----------

RSS = b"""<?xml version="1.0"?><rss><channel>
<item><title>Lanzan un nuevo cohete - Diario Uno</title><source>Diario Uno</source>
<pubDate>Mon, 17 Nov 2026 13:00:00 GMT</pubDate><link>https://example.com/1</link></item>
<item><title>Otra noticia</title><source>Fuente Dos</source><link>https://example.com/2</link></item>
</channel></rss>"""


class _FakeResponse:
    content = RSS


def test_news_parses_rss_and_strips_source_suffix(monkeypatch):
    calls = []

    def fake_get(url, params=None):
        calls.append((url, params))
        return _FakeResponse()

    monkeypatch.setattr(news, "get", fake_get)
    headlines = news.get_news("tecnología", limit=5)
    assert headlines[0].title == "Lanzan un nuevo cohete"
    assert headlines[0].source == "Diario Uno"
    assert headlines[0].published  # fecha local formateada
    assert "TECHNOLOGY" in calls[0][0]

    news.get_news("béisbol", limit=1)
    assert calls[1][1]["q"] == "béisbol"


# ---------- divisas ----------


def test_currency_converts_with_aliases_and_caches(monkeypatch):
    currency._cache.clear()
    calls = []

    def fake_get_json(url, params=None):
        calls.append(url)
        return {"result": "success", "rates": {"DOP": 60.5, "EUR": 0.9}, "time_last_update_utc": "hoy"}

    monkeypatch.setattr(currency, "get_json", fake_get_json)
    result = currency.convert(10, "dólares", "pesos dominicanos")
    assert result["from"] == "USD" and result["to"] == "DOP"
    assert result["result"] == pytest.approx(605)
    currency.convert(1, "USD", "EUR")
    assert len(calls) == 1  # la segunda usa la caché

    with pytest.raises(WebError):
        currency.convert(1, "USD", "ZZZ")
    with pytest.raises(WebError):
        currency.normalize("no-es-moneda")


# ---------- registro ----------


def test_new_tools_are_registered():
    names = {t.name for t in tool_registry.list_tools()}
    for name in ("calculate", "generate_password", "open_website", "set_volume", "lock_computer"):
        assert name in names
    # Con WEB_ENABLED (por defecto) también las que usan internet.
    for name in ("get_weather", "get_news", "convert_currency"):
        assert name in names


# ---------- personalidad ampliada ----------


def test_profile_defaults_and_new_fields(db_session):
    profile = get_profile(db_session)
    assert profile.assistant_name == "ATLAS"
    assert profile.formality == "tu"
    updated = update_profile(
        db_session,
        PersonalityUpdate(assistant_name=" JARVIS ", user_name="Adal", formality="usted", humor="frecuente",
                          home_city="Santiago"),
    )  # fmt: skip
    assert updated.assistant_name == "JARVIS"
    assert updated.user_name == "Adal"


@pytest.mark.parametrize("field", ["formality", "humor"])
def test_profile_rejects_invalid_choices(field):
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        PersonalityUpdate(**{field: "cualquiera"})
    with pytest.raises(ValidationError):
        PersonalityUpdate(assistant_name="   ")


def test_system_prompt_uses_name_formality_city_and_time(db_session):
    profile = update_profile(
        db_session,
        PersonalityUpdate(assistant_name="JARVIS", user_name="Adal", formality="usted", home_city="Santiago"),
    )
    prompt = build_system_prompt(profile, now=datetime(2026, 11, 17, 20, 5))
    assert prompt.startswith("Eres JARVIS")
    assert "Adal" in prompt and "usted" in prompt and "Santiago" in prompt
    assert "martes 17 de noviembre de 2026, 20:05 (noche)" in prompt


def test_describe_now_parts_of_day():
    assert describe_now(datetime(2026, 1, 5, 7, 0)).endswith("(mañana)")
    assert describe_now(datetime(2026, 1, 5, 15, 0)).endswith("(tarde)")
    assert describe_now(datetime(2026, 1, 5, 2, 0)).endswith("(noche)")


def test_personality_api_round_trip(client, auth_headers):
    response = client.put(
        "/api/v1/settings/personality", json={"user_name": "Adal", "humor": "ninguno"}, headers=auth_headers
    )
    assert response.status_code == 200
    body = client.get("/api/v1/settings/personality", headers=auth_headers).json()
    assert body["user_name"] == "Adal" and body["humor"] == "ninguno" and body["assistant_name"] == "ATLAS"


# ---------- migración de columnas ----------


def test_add_missing_columns_upgrades_an_old_personality_table():
    from app.core.database import add_missing_columns

    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    with engine.begin() as conn:
        conn.execute(
            text(
                "CREATE TABLE personality_profiles (id INTEGER PRIMARY KEY, tone VARCHAR(200), "
                "verbosity VARCHAR(20), custom_instructions TEXT)"
            )
        )
        conn.execute(text("INSERT INTO personality_profiles (tone, verbosity, custom_instructions) VALUES ('x','breve','')"))

    added = add_missing_columns(engine)
    assert "personality_profiles.assistant_name" in added
    columns = {c["name"] for c in inspect(engine).get_columns("personality_profiles")}
    assert {"assistant_name", "user_name", "formality", "humor", "home_city"} <= columns
    with engine.connect() as conn:
        row = conn.execute(text("SELECT assistant_name, formality, user_name FROM personality_profiles")).one()
    assert tuple(row) == ("ATLAS", "tu", "")
    assert add_missing_columns(engine) == []  # idempotente


# ---------- widgets ----------


def test_weather_widget_requires_login_and_city(client, auth_headers, monkeypatch):
    monkeypatch.setattr(weather, "get_json", _fake_get_json)
    monkeypatch.setattr(tools, "get_settings", lambda: type("S", (), {"home_place": ""})())
    assert client.get("/api/v1/widgets/weather").status_code in (401, 403)
    assert client.get("/api/v1/widgets/weather", headers=auth_headers).status_code == 404

    response = client.get("/api/v1/widgets/weather?place=Santo Domingo, República Dominicana", headers=auth_headers)
    assert response.status_code == 200
    assert response.json()["icon"] == "partly"


def test_news_widget_reports_service_errors(client, auth_headers, monkeypatch):
    def broken(url, params=None):
        raise WebError("sin internet")

    monkeypatch.setattr(news, "get", broken)
    response = client.get("/api/v1/widgets/news", headers=auth_headers)
    assert response.status_code == 502
    assert "sin internet" in response.json()["detail"]
