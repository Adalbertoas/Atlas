"""Tests de la limpieza de Markdown antes del TTS (Fase 17).

El motivo original: la voz leía "asterisco asterisco importante asterisco
asterisco" y dictaba las URLs carácter por carácter.
"""
from __future__ import annotations

from app.voice.markdown_speech import markdown_to_speech


def test_bold_asterisks_are_not_spoken():
    assert markdown_to_speech("Esto es **importante** de verdad") == "Esto es importante de verdad."


def test_underscore_bold_and_italic():
    assert markdown_to_speech("__fuerte__ y _suave_") == "fuerte y suave."


def test_bold_italic_combined():
    assert markdown_to_speech("***muy fuerte***") == "muy fuerte."


def test_strikethrough():
    assert markdown_to_speech("~~tachado~~") == "tachado."


def test_underscores_inside_words_are_left_alone():
    """`get_system_info` no debe convertirse en "getsysteminfo"."""
    assert "get_system_info" in markdown_to_speech("Usé get_system_info para eso")


def test_headings_lose_the_hashes():
    assert markdown_to_speech("## Resumen del día") == "Resumen del día."


def test_links_keep_the_text_and_drop_the_url():
    result = markdown_to_speech("Mirá [la documentación](https://example.com/a/b?c=1)")
    assert "la documentación" in result
    assert "example.com" not in result
    assert "http" not in result


def test_bare_urls_are_announced_not_dictated():
    result = markdown_to_speech("Está en https://open.spotify.com/track/abc123")
    assert "spotify.com" not in result
    assert "enlace" in result


def test_code_blocks_are_announced_not_dictated():
    result = markdown_to_speech("Probá esto:\n```python\nfor i in range(10):\n    print(i)\n```")
    assert "print" not in result
    assert "bloque de código" in result


def test_inline_code_keeps_its_content():
    assert "atlas.db" in markdown_to_speech("El archivo es `atlas.db`")


def test_bullets_become_sentences_with_pauses():
    """Sin esto la lista entera se lee como una sola frase interminable."""
    result = markdown_to_speech("Tenés:\n- Pan\n- Leche\n- Café")
    assert "-" not in result
    assert result.count(".") >= 3


def test_numbered_lists_keep_the_number():
    result = markdown_to_speech("1. Primero\n2. Segundo")
    assert "1." in result and "2." in result


def test_horizontal_rules_disappear():
    assert markdown_to_speech("Hola\n\n---\n\nChau") == "Hola. Chau."


def test_blockquotes_lose_the_marker():
    assert markdown_to_speech("> Una cita") == "Una cita."


def test_emoji_are_removed():
    """Los motores de voz los nombran ("cara sonriente") e interrumpen la frase."""
    result = markdown_to_speech("Listo ✅ todo bien 🎉")
    assert "✅" not in result and "🎉" not in result
    assert "todo bien" in result


def test_tables_lose_the_pipes():
    result = markdown_to_speech("| Nombre | Estado |\n| --- | --- |\n| Luz | on |")
    assert "|" not in result
    assert "Luz" in result


def test_existing_punctuation_is_not_duplicated():
    assert markdown_to_speech("¿Cómo estás?") == "¿Cómo estás?"


def test_empty_input_is_safe():
    assert markdown_to_speech("") == ""
    assert markdown_to_speech(None) == ""


def test_plain_text_passes_through():
    assert markdown_to_speech("Son las tres de la tarde.") == "Son las tres de la tarde."


def test_speak_endpoint_strips_markdown(client, auth_headers, monkeypatch):
    """El endpoint tiene que limpiar antes de sintetizar, no el cliente."""
    captured = {}

    from app.voice.mock_provider import MockTTSProvider

    original = MockTTSProvider.synthesize

    def spy(self, text):
        captured["text"] = text
        return original(self, text)

    monkeypatch.setattr(MockTTSProvider, "synthesize", spy)

    response = client.post(
        "/api/v1/voice/speak", json={"text": "Esto es **muy** importante"}, headers=auth_headers
    )
    assert response.status_code == 200
    assert "**" not in captured["text"]
    assert "muy importante" in captured["text"]
