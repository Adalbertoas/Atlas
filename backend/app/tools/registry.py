"""ToolRegistry: registro central de herramientas disponibles (sección 4).

Permite agregar nuevas capacidades sin tocar el Orchestrator: basta con
crear una Tool y registrarla aquí.
"""
from __future__ import annotations

from app.ai.base import ToolSchema
from app.tools.base import Tool


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, Tool] = {}

    def register(self, tool: Tool) -> None:
        if tool.name in self._tools:
            raise ValueError(f"La tool '{tool.name}' ya está registrada.")
        self._tools[tool.name] = tool

    def get(self, name: str) -> Tool | None:
        return self._tools.get(name)

    def list_tools(self) -> list[Tool]:
        return list(self._tools.values())

    def to_ai_schemas(self) -> list[ToolSchema]:
        return [t.schema() for t in self._tools.values()]


def build_default_registry() -> ToolRegistry:
    """Instancia el registry con las tools base de ATLAS (V1: sección 25;
    Fase 4: + control de Windows, sección 12)."""
    from app.tools.computer.close_application import CloseApplicationTool
    from app.tools.computer.open_application import OpenApplicationTool
    from app.tools.computer.open_file import OpenFileTool
    from app.tools.filesystem.list_files import ListFilesTool
    from app.tools.filesystem.search_files import SearchFilesTool
    from app.tools.media.control_media import ControlMediaTool
    from app.tools.automation.run_routine import RunRoutineTool
    from app.tools.memory_tools.create_memory import CreateMemoryTool
    from app.tools.memory_tools.search_memory import SearchMemoryTool
    from app.tools.smart_home.control_room import ControlRoomTool
    from app.tools.smart_home.list_devices import ListDevicesTool
    from app.tools.smart_home.set_device_state import SetDeviceStateTool
    from app.tools.system.get_current_time import GetCurrentTimeTool
    from app.tools.system.get_system_info import GetSystemInfoTool
    from app.tools.system.list_processes import ListProcessesTool
    from app.tools.vision.analyze_screenshot import AnalyzeScreenshotTool
    from app.config import get_settings
    from app.tools.briefing.daily_briefing import DailyBriefingTool
    from app.tools.computer.clipboard import ReadClipboardTool, WriteClipboardTool
    from app.tools.computer.manage_window import ManageWindowTool
    from app.tools.computer.save_screenshot import SaveScreenshotTool
    from app.tools.everyday.everyday_tools import (
        CalculateTool,
        ConvertCurrencyTool,
        GeneratePasswordTool,
        GetNewsTool,
        GetWeatherTool,
        LockComputerTool,
        OpenWebsiteTool,
        SetVolumeTool,
    )
    from app.tools.filesystem.search_documents import SearchDocumentsTool
    from app.tools.reminders.reminder_tools import CancelReminderTool, CreateReminderTool, ListRemindersTool
    from app.tools.web.web_tools import ReadWebPageTool, WebSearchTool
    from app.tools.world.alerts import CreateWorldAlertTool, DeleteWorldAlertTool, ListWorldAlertsTool
    from app.tools.world.query_world import QueryWorldTool
    from app.tools.world.show_world_view import ShowWorldViewTool
    from app.world.client import get_gods_eye_client
    from app.world.state import world_view_state
    from app.events.bus import event_bus
    from app.smart_home.provider_factory import get_smart_home_provider
    from app.vision.provider_factory import get_vision_provider

    smart_home_provider = get_smart_home_provider()
    vision_provider = get_vision_provider()

    registry = ToolRegistry()
    for tool in (
        GetSystemInfoTool(),
        GetCurrentTimeTool(),
        OpenApplicationTool(),
        CloseApplicationTool(),
        ListProcessesTool(),
        OpenFileTool(),
        ControlMediaTool(),
        ListFilesTool(),
        SearchFilesTool(),
        CreateMemoryTool(),
        SearchMemoryTool(),
        ListDevicesTool(smart_home_provider),
        SetDeviceStateTool(smart_home_provider, event_bus),
        ControlRoomTool(smart_home_provider, event_bus),
        AnalyzeScreenshotTool(vision_provider),
        ReadClipboardTool(),
        WriteClipboardTool(),
        ManageWindowTool(),
        SaveScreenshotTool(),
        SearchDocumentsTool(),
        CreateReminderTool(),
        ListRemindersTool(),
        CancelReminderTool(),
        CalculateTool(),
        GeneratePasswordTool(),
        OpenWebsiteTool(),
        SetVolumeTool(),
        LockComputerTool(),
    ):
        registry.register(tool)

    settings = get_settings()
    if settings.web_enabled:
        registry.register(WebSearchTool(settings.brave_api_key))
        registry.register(ReadWebPageTool())
        # Servicios públicos sin clave (Open-Meteo, Google News, open.er-api.com).
        registry.register(GetWeatherTool())
        registry.register(GetNewsTool())
        registry.register(ConvertCurrencyTool())

    gods_eye_client = get_gods_eye_client()
    if gods_eye_client is not None:
        registry.register(QueryWorldTool(gods_eye_client, world_view_state))
        registry.register(ShowWorldViewTool(gods_eye_client, world_view_state))
        registry.register(CreateWorldAlertTool())
        registry.register(ListWorldAlertsTool())
        registry.register(DeleteWorldAlertTool())

    # Creatividad: imágenes por internet y dibujos vectoriales con la IA configurada.
    from app.tools.creative.creative_tools import DrawVectorTool, GenerateImageTool

    if settings.web_enabled:
        registry.register(GenerateImageTool())
    if settings.ai_provider != "mock":
        registry.register(DrawVectorTool())

    # Sin Gods Eye View el briefing sale igual, solo que sin el clima.
    registry.register(DailyBriefingTool(gods_eye_client, settings.home_place, event_bus))

    # run_routine se registra al final: necesita una referencia al propio
    # registry (para resolver las tools de cada acción de la rutina) —
    # el objeto ya existe en este punto aunque todavía se esté llenando.
    registry.register(RunRoutineTool(registry, event_bus))
    return registry


# Instancia única a nivel de proceso, inyectada vía app.api.deps.
tool_registry = build_default_registry()
