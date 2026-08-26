from __future__ import annotations

from app.gestures.mouse_controller import MouseController
from app.security.auth import create_access_token, is_token_valid


def test_update_moves_mouse_to_mapped_screen_position(monkeypatch):
    monkeypatch.setattr("app.gestures.mouse_controller.pyautogui.size", lambda: (1000, 500))
    moves = []
    monkeypatch.setattr("app.gestures.mouse_controller.pyautogui.moveTo", lambda x, y: moves.append((x, y)))
    monkeypatch.setattr("app.gestures.mouse_controller.pyautogui.mouseDown", lambda: None)
    monkeypatch.setattr("app.gestures.mouse_controller.pyautogui.mouseUp", lambda: None)

    controller = MouseController()
    controller.update(x_norm=0.5, y_norm=0.5, pinching=False)

    assert len(moves) == 1
    x, y = moves[0]
    assert 400 < x < 600  # ~mitad de 1000, todavía suavizándose desde el primer frame
    assert 200 < y < 300


def test_update_clamps_out_of_range_coordinates(monkeypatch):
    monkeypatch.setattr("app.gestures.mouse_controller.pyautogui.size", lambda: (1000, 500))
    moves = []
    monkeypatch.setattr("app.gestures.mouse_controller.pyautogui.moveTo", lambda x, y: moves.append((x, y)))

    controller = MouseController()
    controller.update(x_norm=1.5, y_norm=-0.5, pinching=False)

    x, y = moves[0]
    assert 0 <= x <= 1000
    assert 0 <= y <= 500


def test_pinching_triggers_mouse_down_once(monkeypatch):
    monkeypatch.setattr("app.gestures.mouse_controller.pyautogui.size", lambda: (1000, 500))
    monkeypatch.setattr("app.gestures.mouse_controller.pyautogui.moveTo", lambda x, y: None)
    down_calls = []
    monkeypatch.setattr("app.gestures.mouse_controller.pyautogui.mouseDown", lambda: down_calls.append(1))
    monkeypatch.setattr("app.gestures.mouse_controller.pyautogui.mouseUp", lambda: None)

    controller = MouseController()
    controller.update(0.5, 0.5, pinching=True)
    controller.update(0.5, 0.5, pinching=True)  # seguir pellizcando no debe repetir mouseDown

    assert len(down_calls) == 1


def test_releasing_pinch_triggers_mouse_up(monkeypatch):
    monkeypatch.setattr("app.gestures.mouse_controller.pyautogui.size", lambda: (1000, 500))
    monkeypatch.setattr("app.gestures.mouse_controller.pyautogui.moveTo", lambda x, y: None)
    monkeypatch.setattr("app.gestures.mouse_controller.pyautogui.mouseDown", lambda: None)
    up_calls = []
    monkeypatch.setattr("app.gestures.mouse_controller.pyautogui.mouseUp", lambda: up_calls.append(1))

    controller = MouseController()
    controller.update(0.5, 0.5, pinching=True)
    controller.update(0.5, 0.5, pinching=False)

    assert len(up_calls) == 1


def test_release_lifts_stuck_click(monkeypatch):
    monkeypatch.setattr("app.gestures.mouse_controller.pyautogui.size", lambda: (1000, 500))
    monkeypatch.setattr("app.gestures.mouse_controller.pyautogui.moveTo", lambda x, y: None)
    monkeypatch.setattr("app.gestures.mouse_controller.pyautogui.mouseDown", lambda: None)
    up_calls = []
    monkeypatch.setattr("app.gestures.mouse_controller.pyautogui.mouseUp", lambda: up_calls.append(1))

    controller = MouseController()
    controller.update(0.5, 0.5, pinching=True)  # se corta la conexión a mitad de un pellizco
    controller.release()

    assert len(up_calls) == 1


def test_scroll_up_when_delta_positive(monkeypatch):
    monkeypatch.setattr("app.gestures.mouse_controller.pyautogui.size", lambda: (1000, 500))
    scroll_calls = []
    monkeypatch.setattr("app.gestures.mouse_controller.pyautogui.scroll", lambda clicks: scroll_calls.append(clicks))

    controller = MouseController()
    controller.scroll(0.05)

    assert len(scroll_calls) == 1
    assert scroll_calls[0] > 0  # positivo = scroll hacia arriba


def test_scroll_down_when_delta_negative(monkeypatch):
    monkeypatch.setattr("app.gestures.mouse_controller.pyautogui.size", lambda: (1000, 500))
    scroll_calls = []
    monkeypatch.setattr("app.gestures.mouse_controller.pyautogui.scroll", lambda clicks: scroll_calls.append(clicks))

    controller = MouseController()
    controller.scroll(-0.05)

    assert scroll_calls[0] < 0


def test_scroll_ignores_negligible_delta(monkeypatch):
    monkeypatch.setattr("app.gestures.mouse_controller.pyautogui.size", lambda: (1000, 500))
    scroll_calls = []
    monkeypatch.setattr("app.gestures.mouse_controller.pyautogui.scroll", lambda clicks: scroll_calls.append(clicks))

    controller = MouseController()
    controller.scroll(0.00001)  # se redondea a 0 clicks

    assert scroll_calls == []


def test_is_token_valid_accepts_real_token():
    token = create_access_token()
    assert is_token_valid(token) is True


def test_is_token_valid_rejects_garbage():
    assert is_token_valid("no-soy-un-jwt") is False
