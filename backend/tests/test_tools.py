from __future__ import annotations

from pathlib import Path

from app.tools.base import ToolContext
from app.tools.computer.close_application import CloseApplicationTool
from app.tools.computer.open_application import OpenApplicationTool
from app.tools.computer.open_file import OpenFileTool
from app.tools.filesystem.list_files import ListFilesTool
from app.tools.media.control_media import ControlMediaTool
from app.tools.system.get_current_time import GetCurrentTimeTool
from app.tools.system.get_system_info import GetSystemInfoTool
from app.tools.system.list_processes import ListProcessesTool


def test_get_current_time_returns_success(db_session):
    tool = GetCurrentTimeTool()
    result = tool.execute({}, ToolContext(db=db_session))
    assert result.success
    assert result.data


def test_get_system_info_returns_metrics(db_session):
    tool = GetSystemInfoTool()
    result = tool.execute({}, ToolContext(db=db_session))
    assert result.success
    assert "cpu_percent" in result.data
    assert "ram_percent" in result.data


def test_open_application_rejects_unknown_app(db_session):
    tool = OpenApplicationTool()
    result = tool.execute({"application_name": "algo-inventado-peligroso"}, ToolContext(db=db_session))
    assert not result.success
    assert "permitidas" in result.error


def test_list_files_on_home_directory(db_session):
    tool = ListFilesTool()
    result = tool.execute({}, ToolContext(db=db_session))
    assert result.success
    assert "entries" in result.data


def test_list_processes_returns_running_processes(db_session):
    tool = ListProcessesTool()
    result = tool.execute({}, ToolContext(db=db_session))
    assert result.success
    assert len(result.data) > 0
    assert "pid" in result.data[0]
    assert "memory_mb" in result.data[0]


def test_close_application_reports_when_process_not_found(db_session):
    tool = CloseApplicationTool()
    result = tool.execute({"process_name": "proceso-que-no-existe-xyz"}, ToolContext(db=db_session))
    assert not result.success
    assert "no encontré" in result.error.lower()


def test_close_application_resolves_known_alias(db_session, monkeypatch):
    # "calculadora" corre como CalculatorApp.exe, no como "calculadora.exe" —
    # sin el alias, esta búsqueda nunca encontraría el proceso real.
    seen_queries = []

    def fake_process_iter(_attrs):
        seen_queries.append(True)
        return []

    monkeypatch.setattr("app.tools.computer.close_application.psutil.process_iter", fake_process_iter)
    tool = CloseApplicationTool()
    result = tool.execute({"process_name": "calculadora"}, ToolContext(db=db_session))
    assert not result.success
    assert "calculatorapp" in result.error.lower()


def test_open_file_rejects_missing_file(db_session):
    tool = OpenFileTool()
    result = tool.execute({"path": "C:/ruta/que/no/existe.txt"}, ToolContext(db=db_session))
    assert not result.success


def test_open_file_rejects_executable_extension(db_session, tmp_path):
    fake_exe = tmp_path / "algo.exe"
    fake_exe.write_bytes(b"MZ")
    tool = OpenFileTool()
    result = tool.execute({"path": str(fake_exe)}, ToolContext(db=db_session))
    assert not result.success
    assert "seguridad" in result.error.lower()


def test_open_file_opens_allowed_extension(db_session, tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr("app.tools.computer.open_file.os.startfile", lambda p: calls.append(p))

    target = tmp_path / "nota.txt"
    target.write_text("hola")
    tool = OpenFileTool()
    result = tool.execute({"path": str(target)}, ToolContext(db=db_session))
    assert result.success
    assert len(calls) == 1


def test_control_media_rejects_unknown_action(db_session):
    tool = ControlMediaTool()
    result = tool.execute({"action": "algo-invalido"}, ToolContext(db=db_session))
    assert not result.success


def test_control_media_executes_known_action(db_session, monkeypatch):
    calls = []
    monkeypatch.setattr("app.tools.media.control_media._press_media_key", lambda vk: calls.append(vk))

    tool = ControlMediaTool()
    result = tool.execute({"action": "play_pause"}, ToolContext(db=db_session))
    assert result.success
    assert calls == [0xB3]
