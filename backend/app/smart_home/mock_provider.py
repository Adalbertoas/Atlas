"""MockSmartHomeProvider: dispositivos en memoria, sin hardware real.

Mismo criterio que MockProvider de IA / MockSTTProvider: permite correr
tests y desarrollar sin depender de una instancia real de Home Assistant.
"""
from __future__ import annotations

from app.smart_home.base import DeviceType, SmartDevice, SmartHomeProvider


def _seed_devices() -> dict[str, SmartDevice]:
    devices = [
        SmartDevice(id="light.sala", name="Luz Sala", room=None, type=DeviceType.LIGHT, state="off"),
        SmartDevice(id="switch.enchufe_oficina", name="Enchufe Oficina", room=None, type=DeviceType.SWITCH, state="off"),
        SmartDevice(id="lock.puerta_principal", name="Puerta Principal", room=None, type=DeviceType.LOCK, state="locked"),
        SmartDevice(id="climate.termostato", name="Termostato", room=None, type=DeviceType.CLIMATE, state="21", capabilities={"temperature": 21}),
    ]
    return {d.id: d for d in devices}


class MockSmartHomeProvider(SmartHomeProvider):
    def __init__(self) -> None:
        self._devices = _seed_devices()

    def list_devices(self) -> list[SmartDevice]:
        return list(self._devices.values())

    def get_device(self, device_id: str) -> SmartDevice | None:
        return self._devices.get(device_id)

    def set_state(self, device_id: str, action: str, value: float | str | None = None) -> SmartDevice:
        device = self._devices.get(device_id)
        if device is None:
            raise KeyError(f"Dispositivo '{device_id}' no encontrado.")

        if action == "turn_on":
            device.state = "on"
        elif action == "turn_off":
            device.state = "off"
        elif action == "lock":
            device.state = "locked"
        elif action == "unlock":
            device.state = "unlocked"
        elif action == "set_temperature":
            device.state = str(value)
            device.capabilities["temperature"] = value
        elif action == "set_brightness":
            device.capabilities["brightness"] = value
        else:
            raise ValueError(f"Acción '{action}' no soportada.")

        return device
