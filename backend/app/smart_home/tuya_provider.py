"""SmartHomeProvider real: Tuya Cloud (Fase 12).

Cubre las apps de marca blanca construidas sobre Tuya — entre ellas
**Mercury Smart**, que es la que usa el usuario (su propio soporte
recomienda la app de Tuya como alternativa). También cubre los mismos
dispositivos vinculados a Alexa: Alexa suele ser solo el control, el
aparato sigue siendo Tuya, así que esta integración los alcanza igual.

Docs: https://developer.tuya.com/en/docs/cloud

Se usa el SDK oficial (`tuya-connector-python`) y no `requests` directo
como en `home_assistant_provider.py`: la firma de Tuya es HMAC-SHA256
sobre una cadena que combina método, hash del cuerpo, headers, token,
timestamp y nonce — fácil de implementar mal y difícil de depurar cuando
falla. El SDK lo resuelve y además refresca el token solo.

Configuración necesaria en .env (ver .env.example):
  SMART_HOME_PROVIDER=tuya
  TUYA_ACCESS_ID / TUYA_ACCESS_SECRET  (proyecto Cloud en iot.tuya.com)
  TUYA_ENDPOINT                        (centro de datos de tu región)
  TUYA_UID                             (cuenta de la app vinculada)
"""
from __future__ import annotations

import logging

from app.smart_home.base import DeviceType, SmartDevice, SmartHomeProvider

logger = logging.getLogger(__name__)

# Centros de datos de Tuya. El proyecto Cloud vive en uno solo y la API
# rechaza credenciales que consultan el que no es.
TUYA_ENDPOINTS = {
    "us": "https://openapi.tuyaus.com",
    "eu": "https://openapi.tuyaeu.com",
    "cn": "https://openapi.tuyacn.com",
    "in": "https://openapi.tuyain.com",
}

# Categorías de Tuya -> tipos de ATLAS. Los códigos son los que devuelve la
# API en el campo `category` (https://developer.tuya.com/en/docs/iot/standarddescription).
_CATEGORY_TO_TYPE: dict[str, DeviceType] = {
    "dj": DeviceType.LIGHT,        # bombilla
    "xdd": DeviceType.LIGHT,       # luz de techo
    "dc": DeviceType.LIGHT,        # tira de luces
    "dd": DeviceType.LIGHT,        # tira LED
    "fwd": DeviceType.LIGHT,       # lámpara ambiental
    "tgq": DeviceType.LIGHT,       # dimmer
    "kg": DeviceType.SWITCH,       # interruptor
    "tdq": DeviceType.SWITCH,      # riel DIN
    "cz": DeviceType.PLUG,         # enchufe
    "pc": DeviceType.PLUG,         # zapatilla
    "fs": DeviceType.FAN,          # ventilador
    "fsd": DeviceType.FAN,         # ventilador de techo
    "kt": DeviceType.CLIMATE,      # aire acondicionado
    "wk": DeviceType.THERMOSTAT,   # termostato
    "qn": DeviceType.CLIMATE,      # calefactor
    "ms": DeviceType.LOCK,         # cerradura
    "jtmspro": DeviceType.LOCK,
    "sp": DeviceType.CAMERA,       # cámara
    "wsdcg": DeviceType.SENSOR,    # sensor temperatura/humedad
    "ldcg": DeviceType.SENSOR,     # sensor de luz
    "mcs": DeviceType.SENSOR,      # sensor de puerta
    "pir": DeviceType.SENSOR,      # sensor de movimiento
    "ywbj": DeviceType.SENSOR,     # detector de humo
    "rqbj": DeviceType.SENSOR,     # detector de gas
    "tv": DeviceType.TV,
}

# Códigos de estado que representan el encendido/apagado principal. Tuya no
# usa uno solo: depende del tipo de dispositivo y de cuántos canales tenga.
_SWITCH_CODES = ("switch_led", "switch", "switch_1")

# Códigos que valen la pena exponer como capabilities (el resto son ruido:
# temporizadores, contadores internos, modos propietarios).
_INTERESTING_CODES = {
    "bright_value", "bright_value_v2", "brightness",
    "temp_set", "temp_current", "va_temperature", "temp_value",
    "va_humidity", "humidity_value",
    "battery_percentage", "electricity_left",
    "cur_power", "cur_voltage", "cur_current",
    "colour_data", "colour_data_v2", "work_mode",
}


class TuyaNotConfigured(Exception):
    """Faltan credenciales de Tuya en .env."""


def _status_map(status: list[dict]) -> dict:
    """La API devuelve el estado como [{'code': ..., 'value': ...}, ...]."""
    return {item["code"]: item["value"] for item in status or []}


class TuyaSmartHomeProvider(SmartHomeProvider):
    def __init__(self, access_id: str, access_secret: str, endpoint: str, uid: str) -> None:
        if not access_id or not access_secret or not uid:
            raise TuyaNotConfigured(
                "Faltan TUYA_ACCESS_ID / TUYA_ACCESS_SECRET / TUYA_UID en backend/.env. "
                "Creá un proyecto Cloud gratis en iot.tuya.com, vinculá tu cuenta de la app "
                "(Mercury Smart / Tuya Smart) y copiá las credenciales. "
                "O usá SMART_HOME_PROVIDER=mock para trabajar sin hardware real."
            )

        # Import diferido: quien use el provider mock o Home Assistant no
        # tiene por qué necesitar el SDK de Tuya instalado.
        from tuya_connector import TuyaOpenAPI

        self._uid = uid
        self._api = TuyaOpenAPI(endpoint, access_id, access_secret)
        self._api.connect()

    # ---------- helpers ----------

    def _request(self, method: str, path: str, **kwargs) -> dict:
        """Envoltorio único sobre el SDK: normaliza el manejo de errores, que
        Tuya reporta con HTTP 200 y `success: false` en el cuerpo."""
        response = getattr(self._api, method)(path, **kwargs)
        if not response.get("success"):
            raise RuntimeError(
                f"Tuya rechazó {method.upper()} {path}: "
                f"{response.get('msg', response)} (code {response.get('code')})"
            )
        return response

    def _to_device(self, raw: dict) -> SmartDevice:
        status = _status_map(raw.get("status", []))

        # Estado principal: el primer código de encendido que exista. Si el
        # dispositivo no tiene ninguno (un sensor, por ejemplo), se cae a
        # online/offline, que siempre está.
        state = "online" if raw.get("online") else "offline"
        for code in _SWITCH_CODES:
            if code in status:
                state = "on" if status[code] else "off"
                break

        category = raw.get("category", "")
        device_type = _CATEGORY_TO_TYPE.get(category, DeviceType.OTHER)

        # Las cerraduras se reportan trabadas/destrabadas, no on/off — el
        # resto de ATLAS asume ese vocabulario (ver mock_provider).
        if device_type is DeviceType.LOCK:
            state = "unlocked" if status.get("lock_motor_state") else "locked"

        capabilities = {k: v for k, v in status.items() if k in _INTERESTING_CODES}
        capabilities["tuya_category"] = category
        capabilities["online"] = bool(raw.get("online"))

        # Normalizar la temperatura al nombre que ya usa el resto de ATLAS
        # (el dashboard y el mock leen `temperature`).
        for code in ("temp_current", "va_temperature", "temp_set", "temp_value"):
            if code in status:
                value = status[code]
                # Tuya suele mandar décimas de grado en enteros (215 = 21.5°C).
                capabilities["temperature"] = value / 10 if abs(value) > 80 else value
                break

        return SmartDevice(
            id=raw["id"],
            name=raw.get("name") or raw["id"],
            room=None,  # las habitaciones son un concepto propio de ATLAS (ver Fase 5)
            type=device_type,
            state=state,
            capabilities=capabilities,
        )

    def _primary_switch_code(self, device_id: str) -> str:
        """Cuál de los códigos de encendido acepta este dispositivo. Se
        consulta en vivo porque varía por modelo (una bombilla usa
        `switch_led`, una zapatilla `switch_1`)."""
        response = self._request("get", f"/v1.0/devices/{device_id}/functions")
        codes = {f["code"] for f in response.get("result", {}).get("functions", [])}
        for code in _SWITCH_CODES:
            if code in codes:
                return code
        raise ValueError(f"El dispositivo '{device_id}' no expone un interruptor que ATLAS entienda.")

    # ---------- interfaz SmartHomeProvider ----------

    def list_devices(self) -> list[SmartDevice]:
        response = self._request(
            "get", f"/v1.0/users/{self._uid}/devices", params={"page_no": 0, "page_size": 100}
        )
        return [self._to_device(raw) for raw in response.get("result", [])]

    def get_device(self, device_id: str) -> SmartDevice | None:
        try:
            response = self._request("get", f"/v1.0/devices/{device_id}")
        except RuntimeError:
            return None
        result = response.get("result")
        return self._to_device(result) if result else None

    def set_state(self, device_id: str, action: str, value: float | str | None = None) -> SmartDevice:
        if action in ("turn_on", "turn_off"):
            commands = [{"code": self._primary_switch_code(device_id), "value": action == "turn_on"}]
        elif action in ("lock", "unlock"):
            # Las cerraduras Tuya no se abren con un simple booleano: exigen
            # una contraseña temporal por API. Se rechaza explícitamente en
            # vez de fingir que funcionó.
            raise ValueError(
                "Las cerraduras Tuya necesitan un flujo de contraseña temporal que ATLAS "
                "todavía no implementa. Usá la app para esto."
            )
        elif action == "set_brightness":
            # Tuya usa 10..1000 en bright_value_v2; ATLAS habla en porcentaje.
            scaled = max(10, min(1000, round(float(value) * 10)))
            commands = [{"code": "bright_value_v2", "value": scaled}]
        elif action == "set_temperature":
            commands = [{"code": "temp_set", "value": int(float(value))}]
        else:
            raise ValueError(f"Acción '{action}' no soportada por el proveedor Tuya.")

        self._request("post", f"/v1.0/devices/{device_id}/commands", body={"commands": commands})

        device = self.get_device(device_id)
        if device is None:
            raise KeyError(f"Dispositivo '{device_id}' no encontrado tras ejecutar la acción.")
        return device
