"""Portapapeles, ventanas, capturas, búsqueda en documentos, web y privacidad."""
from __future__ import annotations

import zipfile

import pytest
import requests

from app.config import Settings
from app.security.privacy import build_privacy_report
from app.tools.base import ToolContext
from app.tools.computer import clipboard
from app.tools.computer.clipboard import ReadClipboardTool, WriteClipboardTool
from app.tools.computer.manage_window import ManageWindowTool
from app.tools.computer.save_screenshot import SaveScreenshotTool
from app.tools.filesystem import search_documents
from app.tools.filesystem.search_documents import SearchDocumentsTool
from app.tools.web.web_tools import ReadWebPageTool, WebSearchTool
from app.web import client as web

# ---------- portapapeles ----------
# La API de Win32 real se prueba a mano: un test que la use pisaría lo que tengas copiado.


def test_read_clipboard_returns_text_and_truncates(db_session, monkeypatch):
    context = ToolContext(db=db_session)

    monkeypatch.setattr(clipboard, "read_clipboard_text", lambda: "hola mundo")
    assert ReadClipboardTool().execute({}, context).data == "hola mundo"

    monkeypatch.setattr(clipboard, "read_clipboard_text", lambda: None)
    assert "no tiene texto" in ReadClipboardTool().execute({}, context).data

    monkeypatch.setattr(clipboard, "read_clipboard_text", lambda: "x" * 9000)
    data = ReadClipboardTool().execute({}, context).data
    assert len(data) < 6200
    assert "9000 caracteres" in data


def test_clipboard_errors_are_reported_not_raised(db_session, monkeypatch):
    def busy():
        raise OSError("El portapapeles está ocupado por otro programa.")

    monkeypatch.setattr(clipboard, "read_clipboard_text", busy)
    result = ReadClipboardTool().execute({}, ToolContext(db=db_session))
    assert not result.success
    assert "ocupado" in result.error


def test_write_clipboard_passes_the_text(db_session, monkeypatch):
    written = []
    monkeypatch.setattr(clipboard, "write_clipboard_text", written.append)
    context = ToolContext(db=db_session)

    assert WriteClipboardTool().execute({"text": "copiame"}, context).success
    assert written == ["copiame"]
    assert not WriteClipboardTool().execute({"text": ""}, context).success


# ---------- ventanas y capturas ----------


def test_manage_window_rejects_unknown_action_and_missing_window(db_session):
    context = ToolContext(db=db_session)
    assert not ManageWindowTool().execute({"action": "explotar"}, context).success

    result = ManageWindowTool().execute({"action": "maximize", "window": "ventana-que-no-existe-xyz"}, context)
    assert not result.success
    assert "No encontré una ventana" in result.error


def test_save_screenshot_writes_a_png(db_session, tmp_path):
    result = SaveScreenshotTool(directory=tmp_path / "capturas").execute({}, ToolContext(db=db_session))

    assert result.success
    (path,) = (tmp_path / "capturas").glob("captura-*.png")
    assert path.read_bytes().startswith(b"\x89PNG")


# ---------- documentos ----------


def _docx(path, text: str) -> None:
    body = (
        '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body>'
        f"<w:p><w:r><w:t>{text}</w:t></w:r></w:p></w:body></w:document>"
    )
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("word/document.xml", body)


def test_search_documents_finds_text_inside_files(db_session, tmp_path):
    (tmp_path / "notas.txt").write_text("Comprar pan.\nLa garantía vence en marzo de 2027.", encoding="utf-8")
    _docx(tmp_path / "contrato.docx", "Cláusula de GARANTÍA extendida por dos años.")
    (tmp_path / "otra.md").write_text("Nada que ver.", encoding="utf-8")
    (tmp_path / "foto.jpg").write_bytes(b"garantia")  # tipo no soportado: se ignora
    (tmp_path / "node_modules").mkdir()
    (tmp_path / "node_modules" / "lib.txt").write_text("garantía", encoding="utf-8")  # carpeta excluida
    _docx(tmp_path / "~$contrato.docx", "garantía")  # temporal de Word: se ignora

    result = SearchDocumentsTool().execute({"query": "garantía", "path": str(tmp_path)}, ToolContext(db=db_session))

    assert result.success
    found = {match["file"].split("\\")[-1].split("/")[-1]: match for match in result.data["matches"]}
    assert set(found) == {"notas.txt", "contrato.docx"}
    assert "vence en marzo de 2027" in found["notas.txt"]["snippet"]
    assert found["contrato.docx"]["occurrences"] == 1  # no distingue mayúsculas


def test_search_documents_survives_broken_files_and_bad_input(db_session, tmp_path):
    (tmp_path / "roto.docx").write_bytes(b"esto no es un zip")
    (tmp_path / "bien.txt").write_text("presupuesto anual", encoding="utf-8")
    context = ToolContext(db=db_session)

    result = SearchDocumentsTool().execute({"query": "presupuesto", "path": str(tmp_path)}, context)
    assert [m["file"].endswith("bien.txt") for m in result.data["matches"]] == [True]

    assert not SearchDocumentsTool().execute({"query": "a", "path": str(tmp_path)}, context).success
    assert not SearchDocumentsTool().execute({"query": "algo", "path": str(tmp_path / "no-existe")}, context).success


def test_search_documents_stops_at_the_file_limit(db_session, tmp_path, monkeypatch):
    monkeypatch.setattr(search_documents, "MAX_FILES", 3)
    for i in range(6):
        (tmp_path / f"n{i}.txt").write_text("sin coincidencias", encoding="utf-8")

    result = SearchDocumentsTool().execute({"query": "aguja", "path": str(tmp_path)}, ToolContext(db=db_session))

    assert result.data["files_scanned"] == 3
    assert "incompleta" in result.data["note"]


# ---------- web ----------

DDG_HTML = """
<div class="result"><h2><a rel="nofollow" class="result__a"
  href="//duckduckgo.com/l/?uddg=https%3A%2F%2Fexample.com%2Fnota%3Fa%3D1&amp;rut=abc">Sismo de <b>hoy</b></a></h2>
  <a class="result__snippet" href="x">Un sismo de magnitud 6 sacudi&oacute; la costa.</a></div>
<div class="result"><a class="result__a" href="https://duckduckgo.com/y.js?ad=1">Anuncio</a></div>
"""


class _Response:
    def __init__(self, text: str = "", data: dict | None = None) -> None:
        self.text = text
        self._data = data or {}

    def raise_for_status(self) -> None:
        pass

    def json(self) -> dict:
        return self._data


def test_duckduckgo_results_are_parsed_and_ads_dropped(monkeypatch):
    monkeypatch.setattr(requests, "post", lambda *a, **k: _Response(DDG_HTML))

    results, source = web.search("sismo hoy", 5)

    assert source == "DuckDuckGo"
    assert [(r.title, r.url, r.snippet) for r in results] == [
        ("Sismo de hoy", "https://example.com/nota?a=1", "Un sismo de magnitud 6 sacudió la costa.")
    ]


def test_search_falls_back_to_wikipedia_when_blocked(monkeypatch):
    def blocked(*args, **kwargs):
        return _Response("<html>anomaly</html>")  # DuckDuckGo devuelve una página sin resultados

    wiki = {"query": {"search": [{"title": "Terremoto de Lisboa", "snippet": "fue un <b>sismo</b>"}]}}
    monkeypatch.setattr(requests, "post", blocked)
    monkeypatch.setattr(requests, "get", lambda *a, **k: _Response(data=wiki))

    results, source = web.search("terremoto", 3)

    assert source == "Wikipedia"
    assert results[0].url == "https://es.wikipedia.org/wiki/Terremoto_de_Lisboa"
    assert results[0].snippet == "fue un sismo"


def test_brave_is_used_first_when_there_is_a_key(monkeypatch):
    seen = {}

    def fake_get(url, **kwargs):
        seen.update(url=url, token=kwargs["headers"]["X-Subscription-Token"])
        return _Response(data={"web": {"results": [{"title": "Hola", "url": "https://a.com", "description": "<b>x</b>"}]}})

    monkeypatch.setattr(requests, "get", fake_get)

    results, source = web.search("hola", 3, brave_api_key="clave")

    assert source == "Brave"
    assert seen == {"url": "https://api.search.brave.com/res/v1/web/search", "token": "clave"}
    assert results[0].snippet == "x"


def test_web_search_tool_warns_when_only_wikipedia_answered(db_session, monkeypatch):
    result = web.SearchResult("Dólar", "https://es.wikipedia.org/wiki/D%C3%B3lar", "moneda")
    monkeypatch.setattr(web, "search", lambda query, limit, key: ([result], "Wikipedia"))

    text = WebSearchTool().execute({"query": "precio del dólar"}, ToolContext(db=db_session)).data

    assert "no sirven para noticias" in text
    assert "1. Dólar — https://es.wikipedia.org" in text


@pytest.mark.parametrize(
    "url", ["http://127.0.0.1:8000/", "http://localhost:4173/mcp", "http://192.168.1.1/", "http://10.0.0.5/", "ftp://example.com/"]
)
def test_read_page_refuses_internal_addresses(db_session, url, monkeypatch):
    def must_not_fetch(*args, **kwargs):
        raise AssertionError("no debería haber hecho el pedido")

    monkeypatch.setattr(requests, "get", must_not_fetch)

    result = ReadWebPageTool().execute({"url": url}, ToolContext(db=db_session))

    assert not result.success


def test_read_page_refuses_redirects_to_internal_addresses(monkeypatch):
    class Redirect:
        is_redirect = True
        headers = {"location": "http://127.0.0.1:8000/api/v1/memory"}

    monkeypatch.setattr(web.socket, "getaddrinfo", lambda host, port: [(0, 0, 0, "", ("93.184.216.34", 0))] if host == "example.com" else [(0, 0, 0, "", ("127.0.0.1", 0))])
    monkeypatch.setattr(requests, "get", lambda *a, **k: Redirect())

    with pytest.raises(web.WebError, match="internas"):
        web.read_page("https://example.com/")


def test_text_extractor_drops_scripts_and_keeps_the_title():
    extractor = web._TextExtractor()
    extractor.feed(
        "<html><head><title>Mi nota</title><style>p{}</style></head><body><nav>Menú</nav>"
        "<h1>Título</h1><p>Primer   párrafo.</p><script>alert(1)</script><p>Segundo.</p></body></html>"
    )
    assert extractor.title == "Mi nota"
    assert extractor.text() == "Título\nPrimer párrafo.\nSegundo."


# ---------- privacidad ----------


def _destinations(**overrides) -> dict[str, str]:
    settings = Settings(_env_file=None, **overrides)
    return {flow["area"]: flow["destination"] for flow in build_privacy_report(settings)}


def test_privacy_report_with_everything_simulated():
    flows = _destinations(
        ai_provider="mock", stt_provider="mock", tts_provider="mock", vision_provider="mock",
        smart_home_provider="mock", gods_eye_url="", web_enabled=False,
    )  # fmt: skip
    assert flows["Inteligencia (chat)"] == "off"
    assert flows["Mundo"] == "off"
    assert flows["Internet"] == "off"
    assert "external" not in flows.values()


def test_privacy_report_marks_what_leaves_the_pc():
    flows = _destinations(
        ai_provider="anthropic", stt_provider="whisper", tts_provider="kokoro", vision_provider="anthropic",
        smart_home_provider="home_assistant", smart_home_url="http://192.168.1.50:8123",
    )  # fmt: skip
    assert flows["Inteligencia (chat)"] == "external"
    assert flows["Visión"] == "external"
    assert flows["Voz a texto"] == "local"
    assert flows["Texto a voz"] == "local"
    assert flows["Hogar"] == "network"
    assert flows["Mundo"] == "external"
    assert flows["Internet"] == "external"


def test_privacy_report_tells_local_from_remote_ollama():
    assert _destinations(ai_provider="ollama")["Inteligencia (chat)"] == "local"
    remote = _destinations(ai_provider="ollama", ollama_base_url="https://ollama.example.com")
    assert remote["Inteligencia (chat)"] == "external"


def test_privacy_report_warns_when_login_is_off():
    report = build_privacy_report(Settings(_env_file=None, auth_enabled=False))
    access = next(flow for flow in report if flow["area"] == "Acceso a ATLAS")
    assert "Cualquiera conectado a tu red" in access["sends"]


def test_privacy_endpoint(client, auth_headers):
    assert client.get("/api/v1/system/privacy").status_code in (401, 403)
    body = client.get("/api/v1/system/privacy", headers=auth_headers).json()
    assert body["auth_enabled"] is True
    assert {"area", "provider", "destination", "sends"} <= set(body["flows"][0])
