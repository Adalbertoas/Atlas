"""Tests del provider de Tuya (Fase 12).

Mockean el SDK entero — no tocan la nube de Tuya ni necesitan credenciales,
igual criterio que el resto de las integraciones externas.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from app.smart_home.base import DeviceType
from app.smart_home.tuya_provider import TuyaNotConfigured, TuyaSmartHomeProvider


def _ok(result):
    return {"success": True, "result": result}


def _build_provider(api_mock):
    """Construye el provider con el SDK reemplazado por un mock."""
    with patch("tuya_connector.TuyaOpenAPI", return_value=api_mock):
        return TuyaSmartHomeProvider(
            access_id="id", access_secret="secret", endpoint="https://openapi.tuyaus.com", uid="uid123"
        )


# ---------- configuración ----------


def test_requires_credentials():
    for kwargs in (
        {"access_id": "", "access_secret": "s", "uid": "u"},
        {"access_id": "i", "access_secret": "", "uid": "u"},
        {"access_id": "i", "access_secret": "s", "uid": ""},
    ):
        with pytest.raises(TuyaNotConfigured):
            TuyaSmartHomeProvider(endpoint="https://openapi.tuyaus.com", **kwargs)


def test_error_message_mentions_the_missing_env_vars():
    with pytest.raises(TuyaNotConfigured) as exc:
        TuyaSmartHomeProvider(access_id="", access_secret="", endpoint="x", uid="")
    assert "TUYA_ACCESS_ID" in str(exc.value)


# ---------- mapeo de dispositivos ----------


def test_list_devices_maps_categories_and_state():
    api = MagicMock()
    api.get.return_value = _ok(
        [
            {
                "id": "bulb1", "name": "Luz Living", "category": "dj", "online": True,
                "status": [{"code": "switch_led", "value": True}, {"code": "bright_value_v2", "value": 500}],
            },
            {
                "id": "plug1", "name": "Enchufe", "category": "cz", "online": True,
                "status": [{"code": "switch_1", "value": False}],
            },
        ]
    )
    devices = _build_provider(api).list_devices()

    assert devices[0].type is DeviceType.LIGHT
    assert devices[0].state == "on"
    assert devices[0].capabilities["bright_value_v2"] == 500
    assert devices[1].type is DeviceType.PLUG
    assert devices[1].state == "off"


def test_unknown_category_falls_back_to_other():
    api = MagicMock()
    api.get.return_value = _ok([{"id": "x", "name": "Raro", "category": "zzz", "online": True, "status": []}])
    assert _build_provider(api).list_devices()[0].type is DeviceType.OTHER


def test_device_without_switch_reports_connectivity():
    """Un sensor no tiene encendido/apagado: se informa online/offline en vez
    de inventar un estado."""
    api = MagicMock()
    api.get.return_value = _ok(
        [{"id": "s1", "name": "Sensor", "category": "wsdcg", "online": False, "status": []}]
    )
    device = _build_provider(api).list_devices()[0]
    assert device.type is DeviceType.SENSOR
    assert device.state == "offline"


def test_lock_uses_locked_vocabulary():
    """El resto de ATLAS habla de locked/unlocked, no de on/off."""
    api = MagicMock()
    api.get.return_value = _ok(
        [{"id": "l1", "name": "Puerta", "category": "ms", "online": True,
          "status": [{"code": "lock_motor_state", "value": False}]}]
    )
    device = _build_provider(api).list_devices()[0]
    assert device.type is DeviceType.LOCK
    assert device.state == "locked"


def test_temperature_is_normalized_to_celsius():
    """Tuya manda décimas de grado en enteros (215 = 21.5 °C)."""
    api = MagicMock()
    api.get.return_value = _ok(
        [{"id": "t1", "name": "Termo", "category": "wk", "online": True,
          "status": [{"code": "temp_current", "value": 215}]}]
    )
    assert _build_provider(api).list_devices()[0].capabilities["temperature"] == 21.5


def test_plain_temperature_is_left_alone():
    api = MagicMock()
    api.get.return_value = _ok(
        [{"id": "t2", "name": "Termo", "category": "wk", "online": True,
          "status": [{"code": "temp_current", "value": 22}]}]
    )
    assert _build_provider(api).list_devices()[0].capabilities["temperature"] == 22


# ---------- errores ----------


def test_api_failure_raises_with_tuya_message():
    """Tuya devuelve HTTP 200 con success:false — no alcanza con mirar el
    código de estado."""
    api = MagicMock()
    api.get.return_value = {"success": False, "msg": "token invalid", "code": 1010}
    with pytest.raises(RuntimeError, match="token invalid"):
        _build_provider(api).list_devices()


def test_get_device_returns_none_when_missing():
    api = MagicMock()
    api.get.return_value = {"success": False, "msg": "not found", "code": 1106}
    assert _build_provider(api).get_device("nope") is None


# ---------- comandos ----------


def test_turn_on_discovers_the_right_switch_code():
    api = MagicMock()
    api.get.side_effect = [
        _ok({"functions": [{"code": "switch_led"}]}),                      # /functions
        _ok({"id": "b1", "name": "Luz", "category": "dj", "online": True,  # get_device
             "status": [{"code": "switch_led", "value": True}]}),
    ]
    api.post.return_value = _ok(True)

    device = _build_provider(api).set_state("b1", "turn_on")

    sent = api.post.call_args.kwargs["body"]["commands"]
    assert sent == [{"code": "switch_led", "value": True}]
    assert device.state == "on"


def test_brightness_is_scaled_to_tuya_range():
    """ATLAS habla en porcentaje (0-100); Tuya espera 10-1000."""
    api = MagicMock()
    api.get.return_value = _ok({"id": "b1", "name": "Luz", "category": "dj", "online": True, "status": []})
    api.post.return_value = _ok(True)

    _build_provider(api).set_state("b1", "set_brightness", 80)

    assert api.post.call_args.kwargs["body"]["commands"] == [{"code": "bright_value_v2", "value": 800}]


def test_brightness_is_clamped_to_valid_range():
    api = MagicMock()
    api.get.return_value = _ok({"id": "b1", "name": "Luz", "category": "dj", "online": True, "status": []})
    api.post.return_value = _ok(True)
    provider = _build_provider(api)

    provider.set_state("b1", "set_brightness", 0)
    assert api.post.call_args.kwargs["body"]["commands"][0]["value"] == 10

    provider.set_state("b1", "set_brightness", 150)
    assert api.post.call_args.kwargs["body"]["commands"][0]["value"] == 1000


def test_locks_are_rejected_explicitly():
    """Mejor un error claro que fingir que se abrió la puerta."""
    api = MagicMock()
    with pytest.raises(ValueError, match="contraseña temporal"):
        _build_provider(api).set_state("l1", "unlock")


def test_unsupported_action_raises():
    api = MagicMock()
    with pytest.raises(ValueError, match="no soportada"):
        _build_provider(api).set_state("x", "hacer_cafe")


def test_device_without_known_switch_code_raises():
    api = MagicMock()
    api.get.return_value = _ok({"functions": [{"code": "modo_raro"}]})
    with pytest.raises(ValueError, match="interruptor"):
        _build_provider(api).set_state("x", "turn_on")
