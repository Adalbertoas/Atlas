from __future__ import annotations

import io

from PIL import Image

from app.security.permissions import RiskLevel
from app.tools.base import ToolContext
from app.tools.vision.analyze_screenshot import AnalyzeScreenshotTool
from app.vision.mock_provider import MockVisionProvider


def _fake_png_bytes() -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (4, 4), color="blue").save(buffer, format="PNG")
    return buffer.getvalue()


def test_mock_vision_provider_returns_description():
    provider = MockVisionProvider()
    description = provider.analyze(b"fake-image-bytes")
    assert isinstance(description, str)
    assert description


def test_analyze_screenshot_is_high_risk():
    tool = AnalyzeScreenshotTool(MockVisionProvider())
    assert tool.resolve_risk_level({}) == RiskLevel.HIGH_RISK


def test_analyze_screenshot_captures_and_analyzes(db_session, monkeypatch):
    fake_image = Image.new("RGB", (4, 4), color="red")
    monkeypatch.setattr("app.tools.vision.analyze_screenshot.ImageGrab.grab", lambda: fake_image)

    tool = AnalyzeScreenshotTool(MockVisionProvider())
    result = tool.execute({}, ToolContext(db=db_session))

    assert result.success
    assert result.data


def test_analyze_screenshot_reports_capture_failure(db_session, monkeypatch):
    def broken_grab():
        raise RuntimeError("sin entorno gráfico")

    monkeypatch.setattr("app.tools.vision.analyze_screenshot.ImageGrab.grab", broken_grab)

    tool = AnalyzeScreenshotTool(MockVisionProvider())
    result = tool.execute({}, ToolContext(db=db_session))

    assert not result.success
    assert "no pude capturar" in result.error.lower()


def test_vision_analyze_endpoint(client, auth_headers):
    response = client.post(
        "/api/v1/vision/analyze",
        files={"image": ("captura.png", _fake_png_bytes(), "image/png")},
        data={"question": "¿qué hay en la imagen?"},
        headers=auth_headers,
    )
    assert response.status_code == 200
    assert response.json()["description"]
