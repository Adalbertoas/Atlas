"""Creatividad: motores de imagen, dibujos SVG saneados, galería, tools y API."""
from __future__ import annotations

import base64

import httpx
import pytest

from app.ai.base import AIResponse
from app.config import get_settings
from app.creative import gallery, images, service, svg
from app.tools.base import ToolContext
from app.tools.creative.creative_tools import DrawVectorTool, GenerateImageTool

PNG = b"\x89PNG\r\n\x1a\nfake"


@pytest.fixture()
def settings(monkeypatch, tmp_path):
    s = get_settings()
    monkeypatch.setattr(s, "creative_dir", str(tmp_path / "creations"))
    monkeypatch.setattr(s, "web_enabled", True)
    monkeypatch.setattr(s, "openai_api_key", "")
    monkeypatch.setattr(s, "image_default_engine", "auto")
    return s


class FakeProvider:
    def __init__(self, text: str):
        self.text = text
        self.calls = []

    def chat(self, messages, tools=None):
        self.calls.append(messages)
        return AIResponse(text=self.text)


# ---------- SVG ----------

def test_sanitize_strips_scripts_events_and_external_refs():
    dirty = (
        '<svg viewBox="0 0 10 10" onload="alert(1)">'
        "<script>alert(1)</script>"
        '<defs><linearGradient id="g"><stop offset="0"/></linearGradient></defs>'
        '<rect width="10" height="10" fill="url(#g)" onclick="x()"/>'
        '<circle r="2" fill="url(http://evil.example/x.svg#a)"/>'
        '<image href="http://evil.example/track.png"/>'
        '<a href="javascript:alert(1)"><text>hola</text></a>'
        '<foreignObject><div>x</div></foreignObject>'
        "<style>@import url(http://evil.example/a.css); rect{fill:red}</style>"
        "</svg>"
    )
    clean = svg.sanitize_svg(dirty)
    lowered = clean.lower()
    for bad in ("script", "onload", "onclick", "evil.example", "javascript", "foreignobject", "<image", "@import"):
        assert bad not in lowered
    assert 'fill="url(#g)"' in clean  # los degradados internos se conservan
    assert "rect{fill:red}" in clean
    assert clean.startswith("<svg") and 'xmlns="http://www.w3.org/2000/svg"' in clean


def test_sanitize_adds_viewbox_and_rejects_doctype():
    assert 'viewBox="0 0 200 100"' in svg.sanitize_svg('<svg width="200px" height="100"><rect/></svg>')
    with pytest.raises(svg.SvgError):
        svg.sanitize_svg('<!DOCTYPE svg [<!ENTITY a "x">]><svg>&a;</svg>')
    with pytest.raises(svg.SvgError):
        svg.sanitize_svg("<svg><rect></svg>")


def test_draw_extracts_svg_from_chatty_reply():
    provider = FakeProvider('Claro, aquí va:\n```svg\n<svg viewBox="0 0 1536 1024"><rect width="5" height="5"/></svg>\n```')
    drawing = svg.draw(provider, "un rectángulo", aspect="horizontal")
    assert drawing.startswith("<svg") and svg.svg_size(drawing) == (1536, 1024)
    assert 'viewBox="0 0 1536 1024"' in provider.calls[0][1].content  # se pidió el formato


def test_draw_without_svg_fails_cleanly():
    with pytest.raises(svg.SvgError):
        svg.draw(FakeProvider("No puedo dibujar eso."), "algo")


# ---------- motores ----------

def test_auto_engine_prefers_openai_only_with_key(settings, monkeypatch):
    assert images.resolve_engine("auto") == "pollinations"
    monkeypatch.setattr(settings, "openai_api_key", "sk-test")
    assert images.resolve_engine("auto") == "openai"
    monkeypatch.setattr(settings, "image_default_engine", "pollinations")
    assert images.resolve_engine(None) == "pollinations"


def test_openai_without_key_explains_how_to_configure(settings):
    with pytest.raises(images.ImageEngineError, match="OPENAI_API_KEY"):
        images.resolve_engine("openai")


def test_no_internet_no_images(settings, monkeypatch):
    monkeypatch.setattr(settings, "web_enabled", False)
    assert images.available_engines() == []
    with pytest.raises(images.ImageEngineError):
        images.resolve_engine("auto")


def test_pollinations_request_and_style(settings, monkeypatch):
    seen = {}

    def fake_get(url, params=None, **kwargs):
        seen.update(url=url, params=params)
        return httpx.Response(200, content=b"jpeg-bytes", headers={"content-type": "image/jpeg"})

    monkeypatch.setattr(images.httpx, "get", fake_get)
    image = images.generate("a lighthouse at dusk", aspect="vertical", style="acuarela")
    assert image.engine == "pollinations" and image.mime_type == "image/jpeg" and image.data == b"jpeg-bytes"
    assert (seen["params"]["width"], seen["params"]["height"]) == (1024, 1536)
    assert "watercolor" in httpx.URL(seen["url"]).path


def test_pollinations_non_image_is_an_error(settings, monkeypatch):
    monkeypatch.setattr(images.httpx, "get", lambda *a, **k: httpx.Response(502, text="bad gateway"))
    with pytest.raises(images.ImageEngineError, match="HTTP 502"):
        images.generate("a cat")


def test_openai_request_and_errors(settings, monkeypatch):
    monkeypatch.setattr(settings, "openai_api_key", "sk-test")
    sent = {}

    def ok(url, json=None, headers=None, **kwargs):
        sent.update(json=json, headers=headers)
        return httpx.Response(200, json={"data": [{"b64_json": base64.b64encode(PNG).decode()}]})

    monkeypatch.setattr(images.httpx, "post", ok)
    image = images.generate("a red fox", engine="openai", aspect="horizontal")
    assert image.data == PNG and image.mime_type == "image/png"
    assert sent["json"]["size"] == "1536x1024" and sent["headers"]["Authorization"] == "Bearer sk-test"

    monkeypatch.setattr(images.httpx, "post", lambda *a, **k: httpx.Response(400, json={"error": {"message": "rejected by safety system"}}))
    with pytest.raises(images.ImageEngineError, match="safety"):
        images.generate("x y z", engine="openai")
    monkeypatch.setattr(images.httpx, "post", lambda *a, **k: httpx.Response(401, json={}))
    with pytest.raises(images.ImageEngineError, match="clave"):
        images.generate("x y z", engine="openai")


# ---------- galería ----------

def test_gallery_save_list_delete(settings):
    first = gallery.save(PNG, "image/png", "openai", "un zorro rojo", 1024, 1024)
    second = gallery.save(b"<svg/>", "image/svg+xml", "claude", "logo", 1024, 1024)
    assert gallery.path_of(first).read_bytes() == PNG and gallery.path_of(second).suffix == ".svg"
    assert [c.id for c in gallery.recent()] == [second.id, first.id]
    gallery.path_of(first).unlink()  # borrado a mano: desaparece de la galería
    assert [c.id for c in gallery.recent()] == [second.id]
    assert gallery.delete(second.id) and not gallery.path_of(second).exists()
    assert not gallery.delete("../../etc/passwd")


# ---------- tools ----------

def test_generate_image_tool_returns_visible_image(settings, monkeypatch, db_session):
    monkeypatch.setattr(images.httpx, "get", lambda *a, **k: httpx.Response(200, content=b"jpg", headers={"content-type": "image/jpeg"}))
    result = GenerateImageTool().execute({"prompt": "a castle in the clouds", "style": "oleo"}, ToolContext(db=db_session))
    assert result.success and result.images[0].mime_type == "image/jpeg"
    assert base64.b64decode(result.images[0].data) == b"jpg"
    assert "creations" in result.data  # la ruta apunta a la carpeta configurada


def test_generate_image_tool_reports_errors(settings, db_session):
    result = GenerateImageTool().execute({"prompt": "a cat", "engine": "openai"}, ToolContext(db=db_session))
    assert not result.success and "OPENAI_API_KEY" in result.error


def test_draw_vector_tool(settings, monkeypatch, db_session):
    monkeypatch.setattr(service, "_drawing_provider", lambda: FakeProvider('<svg viewBox="0 0 64 64"><circle r="9"/></svg>'))
    result = DrawVectorTool().execute({"description": "un logo circular"}, ToolContext(db=db_session))
    assert result.success and result.images[0].mime_type == "image/svg+xml"
    assert gallery.recent()[0].engine == "claude"


# ---------- API ----------

def test_creative_api_flow(client, auth_headers, settings, monkeypatch):
    from io import BytesIO

    from PIL import Image

    buffer = BytesIO()
    Image.new("RGB", (800, 600), "teal").save(buffer, "JPEG")
    jpg = buffer.getvalue()
    monkeypatch.setattr(images.httpx, "get", lambda *a, **k: httpx.Response(200, content=jpg, headers={"content-type": "image/jpeg"}))
    info = client.get("/api/v1/creative/engines", headers=auth_headers).json()
    assert "pollinations" in info["available"] and "foto" in info["styles"]

    made = client.post("/api/v1/creative/image", json={"prompt": "neon city", "engine": "pollinations"}, headers=auth_headers)
    assert made.status_code == 200 and base64.b64decode(made.json()["data"]) == jpg

    listed = client.get("/api/v1/creative/gallery", headers=auth_headers).json()
    assert listed[0]["id"] == made.json()["id"] and "data" not in listed[0]
    with Image.open(BytesIO(base64.b64decode(listed[0]["thumb"]))) as thumb:
        assert max(thumb.size) <= 384  # miniatura, no la imagen completa
    full = client.get(f"/api/v1/creative/gallery/{made.json()['id']}", headers=auth_headers).json()
    assert base64.b64decode(full["data"]) == jpg

    failed = client.post("/api/v1/creative/image", json={"prompt": "neon city", "engine": "openai"}, headers=auth_headers)
    assert failed.status_code == 422 and "OPENAI_API_KEY" in failed.json()["detail"]

    assert client.delete(f"/api/v1/creative/gallery/{made.json()['id']}", headers=auth_headers).status_code == 200
    assert client.get("/api/v1/creative/gallery", headers=auth_headers).json() == []
    assert client.get("/api/v1/creative/gallery").status_code in (401, 403)


def test_enhance_prompt(client, auth_headers, monkeypatch):
    provider = FakeProvider('"A lone lighthouse on a cliff during a violent thunderstorm, oil painting"')
    monkeypatch.setattr(service, "_enhance_provider", lambda: provider)
    response = client.post("/api/v1/creative/enhance", json={"prompt": "faro en tormenta, óleo"}, headers=auth_headers)
    assert response.json()["prompt"].startswith("A lone lighthouse")  # sin comillas
    assert provider.calls[0][1].content == "faro en tormenta, óleo"
