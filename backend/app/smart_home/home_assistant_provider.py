"""SmartHomeProvider real: Home Assistant, vía su API REST.

Docs: https://developers.home-assistant.io/docs/api/rest/

No usa la API de WebSocket de HA (áreas/registro de entidades) — ver
docs/architecture.md, Fase 5, sobre por qué las habitaciones se manejan en
ATLAS y no se importan de HA.
"""
from __future__ import annotations

import requests

from app.smart_home.base import DeviceType, SmartDevice, SmartHomeProvider

_DOMAIN_TO_TYPE: dict[str, DeviceType] = {
    "light": DeviceType.LIGHT,
    "switch": DeviceType.SWITCH,
    "lock": DeviceType.LOCK,
    "climate": DeviceType.CLIMATE,
    "media_player": DeviceType.TV,
    "fan": DeviceType.FAN,
    "camera": DeviceType.CAMERA,
    "sensor": DeviceType.SENSOR,
    "binary_sensor": DeviceType.SENSOR,
}

# Servicio de HA a llamar por acción lógica de ATLAS, por dominio.
_ACTION_TO_SERVICE: dict[str, dict[str, str]] = {
    "turn_on": {"light": "turn_on", "switch": "turn_on", "fan": "turn_on", "media_player": "turn_on"},
    "turn_off": {"light": "turn_off", "switch": "turn_off", "fan": "turn_off", "media_player": "turn_off"},
    "lock": {"lock": "lock"},
    "unlock": {"lock": "unlock"},
    "set_temperature": {"climate": "set_temperature"},
    "set_brightness": {"light": "turn_on"},  # brightness va como parámetro extra del mismo servicio
}


def _domain_of(entity_id: str) -> str:
    return entity_id.split(".", 1)[0]


class HomeAssistantProvider(SmartHomeProvider):
    def __init__(self, base_url: str, token: str, timeout: int = 10) -> None:
        if not base_url or not token:
            raise ValueError(
                "SMART_HOME_URL/SMART_HOME_TOKEN vacíos. Configura tu Home Assistant en .env "
                "o usa SMART_HOME_PROVIDER=mock."
            )
        self._base_url = base_url.rstrip("/")
        self._headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
        self._timeout = timeout

    def _to_device(self, entity: dict) -> SmartDevice:
        entity_id = entity["entity_id"]
        domain = _domain_of(entity_id)
        attributes = entity.get("attributes", {})
        return SmartDevice(
            id=entity_id,
            name=attributes.get("friendly_name", entity_id),
            room=None,  # las habitaciones se resuelven en app.smart_home.service, no acá
            type=_DOMAIN_TO_TYPE.get(domain, DeviceType.OTHER),
            state=entity.get("state", "unknown"),
            capabilities={k: v for k, v in attributes.items() if k != "friendly_name"},
        )

    def list_devices(self) -> list[SmartDevice]:
        response = requests.get(f"{self._base_url}/api/states", headers=self._headers, timeout=self._timeout)
        response.raise_for_status()
        return [self._to_device(e) for e in response.json()]

    def get_device(self, device_id: str) -> SmartDevice | None:
        response = requests.get(
            f"{self._base_url}/api/states/{device_id}", headers=self._headers, timeout=self._timeout
        )
        if response.status_code == 404:
            return None
        response.raise_for_status()
        return self._to_device(response.json())

    def set_state(self, device_id: str, action: str, value: float | str | None = None) -> SmartDevice:
        domain = _domain_of(device_id)
        service = _ACTION_TO_SERVICE.get(action, {}).get(domain)
        if service is None:
            raise ValueError(f"Acción '{action}' no soportada para dispositivos de tipo '{domain}'.")

        payload: dict = {"entity_id": device_id}
        if action == "set_temperature":
            payload["temperature"] = value
        elif action == "set_brightness":
            payload["brightness_pct"] = value

        response = requests.post(
            f"{self._base_url}/api/services/{domain}/{service}",
            headers=self._headers,
            json=payload,
            timeout=self._timeout,
        )
        response.raise_for_status()

        device = self.get_device(device_id)
        if device is None:
            raise KeyError(f"Dispositivo '{device_id}' no encontrado tras ejecutar la acción.")
        return device
