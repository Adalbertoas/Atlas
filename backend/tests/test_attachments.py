"""Adjuntos en el chat (imágenes/PDF) y la tool create_spreadsheet."""
from __future__ import annotations

import base64
import io

import pytest
from openpyxl import load_workbook
from PIL import Image

from app.ai.anthropic_provider import AnthropicProvider
from app.ai.base import AIAttachment, AIMessage, AIProvider, AIResponse, ToolSchema
from app.core.attachments import MAX_VIEW_AREA, MAX_VIEW_SIDE, AttachmentError, RawAttachment, normalize
from app.core.orchestrator import Orchestrator
from app.events.bus import EventBus
from app.memory.conversation_service import get_history
from app.security.permissions import PermissionManager
from app.tools.base import ToolContext
from app.tools.office.spreadsheet import CreateSpreadsheetTool
from app.tools.registry import build_default_registry
from app.vision.base import VisionProvider


def _png(width: int = 40, height: int = 30, color=(200, 30, 30)) -> str:
    buffer = io.BytesIO()
    Image.new("RGB", (width, height), color).save(buffer, format="PNG")
    return base64.b64encode(buffer.getvalue()).decode("ascii")


# --- normalización ---------------------------------------------------------


def test_small_image_is_accepted_as_is():
    [att] = normalize([RawAttachment("foto.png", "image/png", _png())])
    assert att.kind == "image" and att.mime_type == "image/png" and att.name == "foto.png"


def _size(att: AIAttachment) -> tuple[int, int]:
    return Image.open(io.BytesIO(base64.b64decode(att.data))).size


def test_large_image_is_downscaled_to_what_the_model_sees():
    overview, *tiles = normalize([RawAttachment("grande.jpg", "image/jpeg", _png(5000, 2500))])
    width, height = _size(overview)
    assert not overview.detail and max(width, height) <= MAX_VIEW_SIDE and width * height <= MAX_VIEW_AREA * 1.01
    assert tiles  # foto grande: además van recortes de detalle


def test_tall_receipt_gets_enlarged_strips():
    overview, *tiles = normalize([RawAttachment("ticket.jpg", "image/jpeg", _png(900, 1600))])
    assert [t.detail for t in tiles] == [f"parte {i} de 3, de arriba hacia abajo" for i in (1, 2, 3)]
    assert all(t.name == "ticket.jpg" for t in tiles)
    # Cada franja muestra el texto más grande que la imagen completa.
    assert all(_size(t)[0] > _size(overview)[0] * 1.3 for t in tiles)
    assert all(w * h <= MAX_VIEW_AREA * 1.01 for w, h in map(_size, tiles))


def test_small_or_many_images_get_no_tiles():
    assert len(normalize([RawAttachment("chica.png", "image/png", _png(800, 600))])) == 1
    many = normalize([RawAttachment(f"{i}.png", "image/png", _png(900, 1600)) for i in range(4)])
    assert len(many) == 4 and not any(a.detail for a in many)


def test_data_url_prefix_is_accepted():
    [att] = normalize([RawAttachment("x.png", "image/png", "data:image/png;base64," + _png())])
    assert att.kind == "image"


def test_pdf_is_passed_through():
    raw = b"%PDF-1.4\n%fake\n"
    [att] = normalize([RawAttachment("f.pdf", "application/pdf", base64.b64encode(raw).decode())])
    assert att.kind == "pdf" and base64.b64decode(att.data) == raw


@pytest.mark.parametrize(
    ("item", "fragment"),
    [
        (RawAttachment("a.exe", "application/x-msdownload", base64.b64encode(b"MZ").decode()), "No puedo leer"),
        (RawAttachment("a.png", "image/png", "esto-no-es-base64!!"), "codificado"),
        (RawAttachment("a.png", "image/png", base64.b64encode(b"no soy imagen").decode()), "no es una imagen"),
        (RawAttachment("a.pdf", "application/pdf", base64.b64encode(b"hola").decode()), "PDF"),
    ],
)
def test_invalid_attachments_are_rejected(item, fragment):
    with pytest.raises(AttachmentError, match=fragment):
        normalize([item])


def test_too_many_attachments_are_rejected():
    with pytest.raises(AttachmentError):
        normalize([RawAttachment(f"{i}.png", "image/png", _png()) for i in range(7)])


# --- proveedor de Anthropic ------------------------------------------------


def test_anthropic_request_sends_image_and_pdf_blocks_before_text():
    provider = AnthropicProvider(api_key="sk-ant-test", model="claude-test")
    message = AIMessage(
        role="user",
        content="pasalo a excel",
        attachments=[
            AIAttachment(kind="image", mime_type="image/png", data="AAA", name="t.png"),
            AIAttachment(kind="pdf", mime_type="application/pdf", data="BBB", name="f.pdf"),
        ],
    )
    request = provider._request([AIMessage(role="system", content="sys"), message], None)
    [user] = request["messages"]
    assert [b["type"] for b in user["content"]] == ["image", "document", "text"]
    assert user["content"][0]["source"] == {"type": "base64", "media_type": "image/png", "data": "AAA"}
    assert user["content"][2]["text"] == "pasalo a excel"


def test_anthropic_request_labels_detail_tiles():
    provider = AnthropicProvider(api_key="sk-ant-test", model="claude-test")
    message = AIMessage(
        role="user",
        content="leelo",
        attachments=[
            AIAttachment(kind="image", mime_type="image/png", data="A", name="t.jpg"),
            AIAttachment(kind="image", mime_type="image/png", data="B", name="t.jpg", detail="parte 1 de 3"),
        ],
    )
    [user] = provider._request([message], None)["messages"]
    assert [b["type"] for b in user["content"]] == ["image", "text", "image", "text"]
    assert "Recorte ampliado de 't.jpg' (parte 1 de 3)" in user["content"][1]["text"]


def test_anthropic_request_keeps_plain_text_without_attachments():
    provider = AnthropicProvider(api_key="sk-ant-test", model="claude-test")
    request = provider._request([AIMessage(role="user", content="hola")], None)
    assert request["messages"] == [{"role": "user", "content": "hola"}]


# --- orquestador -----------------------------------------------------------


class _Recorder(AIProvider):
    def __init__(self, supports: bool) -> None:
        self.supports_attachments = supports
        self.seen: list[list[AIMessage]] = []

    def chat(self, messages: list[AIMessage], tools: list[ToolSchema] | None = None) -> AIResponse:
        self.seen.append(list(messages))
        return AIResponse(text="listo")


class _FakeVision(VisionProvider):
    def analyze(self, image_bytes: bytes, question: str | None = None) -> str:
        return "Producto | Precio\nPan | 2"


def _orchestrator(provider: AIProvider) -> Orchestrator:
    return Orchestrator(provider, build_default_registry(), PermissionManager(), EventBus(), vision=_FakeVision())


def _attachment() -> AIAttachment:
    return normalize([RawAttachment("tabla.png", "image/png", _png())])[0]


def test_multimodal_provider_receives_attachments_only_on_current_turn(db_session):
    provider = _Recorder(supports=True)
    orchestrator = _orchestrator(provider)
    first = orchestrator.handle_message(db_session, "", attachments=[_attachment()])
    orchestrator.handle_message(db_session, "gracias", first.conversation_id)

    current = provider.seen[0][-1]
    assert current.attachments and current.content.startswith("Analiza el archivo adjunto.")
    assert all(not m.attachments for m in provider.seen[1])
    stored = get_history(db_session, first.conversation_id)[0].content
    assert "[Adjuntos: tabla.png]" in stored


def test_text_only_provider_gets_vision_description(db_session):
    provider = _Recorder(supports=False)
    _orchestrator(provider).handle_message(db_session, "pasalo a excel", attachments=[_attachment()])
    current = provider.seen[0][-1]
    assert not current.attachments
    assert "[Contenido de 'tabla.png']" in current.content and "Pan | 2" in current.content


# --- API -------------------------------------------------------------------


def test_chat_api_accepts_image_attachment(client, auth_headers):
    response = client.post(
        "/api/v1/chat",
        json={"message": "", "attachments": [{"name": "t.png", "mime_type": "image/png", "data": _png()}]},
        headers=auth_headers,
    )
    assert response.status_code == 200
    assert response.json()["reply"]


def test_chat_api_rejects_unsupported_attachment(client, auth_headers):
    response = client.post(
        "/api/v1/chat",
        json={"message": "x", "attachments": [{"name": "a.zip", "mime_type": "application/zip", "data": "UEsDBA=="}]},
        headers=auth_headers,
    )
    assert response.status_code == 400
    assert "No puedo leer" in response.json()["detail"]


def test_chat_api_rejects_empty_message_without_attachments(client, auth_headers):
    assert client.post("/api/v1/chat", json={"message": "  "}, headers=auth_headers).status_code == 422


# --- create_spreadsheet ----------------------------------------------------


def test_spreadsheet_is_written_with_typed_cells(tmp_path, db_session):
    tool = CreateSpreadsheetTool(directory=tmp_path)
    result = tool.execute(
        {
            "filename": 'gastos: "nov"',
            "open_after": False,
            "sheets": [
                {
                    "name": "Gastos/Nov",
                    "headers": ["Concepto", "Monto (USD)", "Código"],
                    "rows": [["Pan", "1,234.50", "00123"], ["Leche", 3, None], ["Total", "=SUM(B2:B3)", ""]],
                }
            ],
        },
        ToolContext(db=db_session),
    )
    assert result.success, result.error
    path = tmp_path / "gastos nov.xlsx"
    assert str(path) in result.data

    ws = load_workbook(path)["GastosNov"]
    assert [c.value for c in ws[1]] == ["Concepto", "Monto (USD)", "Código"]
    assert ws["B2"].value == 1234.5 and ws["B3"].value == 3
    assert ws["C2"].value == "00123"  # los ceros a la izquierda se conservan
    assert ws["B4"].value == "=SUM(B2:B3)"
    assert ws.freeze_panes == "A2"


def test_invoice_document_layout(tmp_path, db_session):
    result = CreateSpreadsheetTool(directory=tmp_path).execute(
        {
            "filename": "Factura 120",
            "currency_symbol": "RD$",
            "sheets": [
                {
                    "name": "Factura",
                    "title": "BAMBY LIQUOR STORE",
                    "subtitle": "BAMBY S.R.L.",
                    "info": [{"label": "Factura Nro.", "value": "E310000000120"}, {"label": "RNC", "value": "132798791"},
                             {"label": "Cliente", "value": "MONACOT BAR"}, {"label": "Condición", "value": "CONTADO"}],
                    "headers": ["Código", "Descripción", "Cantidad", "Precio unit.", "Subtotal"],
                    "column_formats": ["text", "text", "number", "currency", "currency"],
                    "rows": [["PR000095", "CORONA EXTRA", 24, 100.64, 2415.36], ["PR000102", "JOSE CUERVO", 1, "1,250.00", 1250]],
                    "totals": [
                        {"label": "Subtotal (sin ITBIS)", "sum_of_column": 5},
                        {"label": "ITBIS", "detail": "18%", "value": 659.76},
                        {"label": "TOTAL FACTURA", "value": 4325.12, "highlight": True},
                    ],
                    "notes": ["Anotación a mano: 'normal'."],
                }
            ],
        },
        ToolContext(db=db_session),
    )
    assert result.success, result.error
    [file] = result.files
    assert file.name == "Factura 120.xlsx" and file.size > 0 and file.mime_type.endswith("spreadsheetml.sheet")

    ws = load_workbook(tmp_path / "Factura 120.xlsx")["Factura"]
    cells = {c.value: c for row in ws.iter_rows() for c in row if c.value is not None}
    assert ws["A1"].value == "BAMBY LIQUOR STORE" and ws["A1"].font.bold
    assert "E310000000120" in cells and "132798791" in cells  # identificadores como texto
    assert cells["PR000095"].column == 1 and cells["CORONA EXTRA"].column == 2
    assert cells[1250].number_format.startswith('"RD$"')  # "1,250.00" se convirtió a número
    sum_cell = next(c for v, c in cells.items() if isinstance(v, str) and v.startswith("=SUM(E"))
    assert sum_cell.column == 5
    total_label = cells["TOTAL FACTURA"]
    assert total_label.fill.fgColor.rgb.endswith("FFF2CC")
    assert any(isinstance(v, str) and v.startswith("Generado por ATLAS") for v in cells)
    assert not ws.sheet_view.showGridLines


def test_spreadsheet_never_overwrites(tmp_path, db_session):
    tool = CreateSpreadsheetTool(directory=tmp_path)
    params = {"filename": "tabla", "open_after": False, "sheets": [{"rows": [[1]]}]}
    tool.execute(params, ToolContext(db=db_session))
    tool.execute(params, ToolContext(db=db_session))
    assert sorted(p.name for p in tmp_path.iterdir()) == ["tabla (2).xlsx", "tabla.xlsx"]


def test_spreadsheet_requires_rows(tmp_path, db_session):
    result = CreateSpreadsheetTool(directory=tmp_path).execute({"filename": "x", "sheets": []}, ToolContext(db=db_session))
    assert not result.success


def test_spreadsheet_tool_is_registered():
    assert build_default_registry().get("create_spreadsheet") is not None


# --- descarga de archivos generados -----------------------------------------


def test_files_endpoint_serves_only_output_folder(client, auth_headers, tmp_path, monkeypatch):
    from app.core import outputs

    monkeypatch.setattr(outputs, "output_dir", lambda: tmp_path)
    (tmp_path / "tabla.xlsx").write_bytes(b"PK-fake")
    (tmp_path.parent / "secreto.txt").write_text("no")

    ok = client.get("/api/v1/files/tabla.xlsx", headers=auth_headers)
    assert ok.status_code == 200 and ok.content == b"PK-fake"
    assert "spreadsheetml" in ok.headers["content-type"]
    for bad in ("..%2Fsecreto.txt", "no-existe.xlsx", "~$tabla.xlsx"):
        assert client.get(f"/api/v1/files/{bad}", headers=auth_headers).status_code == 404
    assert client.get("/api/v1/files/tabla.xlsx").status_code in (401, 403)


def test_chat_response_includes_generated_files(db_session, tmp_path):
    from app.ai.base import ToolCall

    class _Calls(AIProvider):
        def __init__(self):
            self.turn = 0

        def chat(self, messages, tools=None):
            self.turn += 1
            if self.turn == 1:
                return AIResponse(tool_calls=[ToolCall(id="x", name="create_spreadsheet", arguments={
                    "filename": "lista", "sheets": [{"headers": ["A"], "rows": [[1]]}]})])
            return AIResponse(text="listo")

    from app.tools.registry import ToolRegistry

    registry = ToolRegistry()
    registry.register(CreateSpreadsheetTool(directory=tmp_path))
    result = Orchestrator(_Calls(), registry, PermissionManager(), EventBus()).handle_message(db_session, "hacé una lista")
    assert [f.name for f in result.files] == ["lista.xlsx"]
