"""Tools que necesitan la PC (Windows). Módulo aparte del registro para que el
agente de la PC las cargue sin armar todo el backend."""
from __future__ import annotations

from app.tools.base import Tool


def build_pc_tools(vision_provider=None) -> list[Tool]:
    """Tools que necesitan la PC (Windows): programas, ventanas, portapapeles,
    pantalla, archivos locales, volumen. Las usa también el agente de la PC."""
    from app.tools.computer.clipboard import ReadClipboardTool, WriteClipboardTool
    from app.tools.computer.close_application import CloseApplicationTool
    from app.tools.computer.manage_window import ManageWindowTool
    from app.tools.computer.open_application import OpenApplicationTool
    from app.tools.computer.open_file import OpenFileTool
    from app.tools.computer.save_screenshot import SaveScreenshotTool
    from app.tools.everyday.everyday_tools import LockComputerTool, OpenWebsiteTool, SetVolumeTool
    from app.tools.filesystem.list_files import ListFilesTool
    from app.tools.filesystem.search_documents import SearchDocumentsTool
    from app.tools.filesystem.search_files import SearchFilesTool
    from app.tools.media.control_media import ControlMediaTool
    from app.tools.system.get_system_info import GetSystemInfoTool
    from app.tools.system.list_processes import ListProcessesTool
    from app.tools.vision.analyze_screenshot import AnalyzeScreenshotTool

    if vision_provider is None:
        from app.vision.provider_factory import get_vision_provider

        vision_provider = get_vision_provider()
    return [
        GetSystemInfoTool(),
        OpenApplicationTool(),
        CloseApplicationTool(),
        ListProcessesTool(),
        OpenFileTool(),
        ControlMediaTool(),
        ListFilesTool(),
        SearchFilesTool(),
        AnalyzeScreenshotTool(vision_provider),
        ReadClipboardTool(),
        WriteClipboardTool(),
        ManageWindowTool(),
        SaveScreenshotTool(),
        SearchDocumentsTool(),
        OpenWebsiteTool(),
        SetVolumeTool(),
        LockComputerTool(),
    ]
