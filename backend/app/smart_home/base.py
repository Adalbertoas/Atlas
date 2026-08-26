"""Interfaz de Smart Home de ATLAS (sección 9 del prompt maestro).

SmartHomeProvider está desacoplado del cerebro de ATLAS: el Orchestrator y
las tools solo conocen esta interfaz, nunca hablan directo con Home
Assistant, MQTT, Matter, etc.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum


class DeviceType(str, Enum):
    LIGHT = "LIGHT"
    SWITCH = "SWITCH"
    PLUG = "PLUG"
    SENSOR = "SENSOR"
    THERMOSTAT = "THERMOSTAT"
    TV = "TV"
    LOCK = "LOCK"
    CAMERA = "CAMERA"
    FAN = "FAN"
    CLIMATE = "CLIMATE"
    OTHER = "OTHER"


# Tipos que pueden participar en acciones masivas por habitación (sección 10:
# "apaga todo en la oficina"). Deliberadamente NO incluye LOCK, CAMERA,
# SENSOR ni CLIMATE/THERMOSTAT — nunca se afectan en bloque, sin importar
# confirmación.
ROOM_BULK_SAFE_TYPES = {DeviceType.LIGHT, DeviceType.SWITCH, DeviceType.PLUG, DeviceType.FAN, DeviceType.TV}


@dataclass
class SmartDevice:
    id: str  # entity_id del proveedor (ej. Home Assistant)
    name: str
    room: str | None
    type: DeviceType
    state: str  # "on" | "off" | valor bruto del proveedor
    capabilities: dict = field(default_factory=dict)  # ej. {"brightness": 80, "temperature": 21}


class SmartHomeProvider(ABC):
    """Interfaz que debe implementar cualquier integración de smart home."""

    @abstractmethod
    def list_devices(self) -> list[SmartDevice]:
        raise NotImplementedError

    @abstractmethod
    def get_device(self, device_id: str) -> SmartDevice | None:
        raise NotImplementedError

    @abstractmethod
    def set_state(self, device_id: str, action: str, value: float | str | None = None) -> SmartDevice:
        """Ejecuta una acción (ej. 'turn_on', 'turn_off', 'set_brightness',
        'set_temperature', 'lock', 'unlock') sobre un dispositivo y devuelve
        su estado resultante."""
        raise NotImplementedError
