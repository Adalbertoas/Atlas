@echo off
rem Levanta todo ATLAS: backend, dashboard, movil y Mundo. Ctrl+C detiene todo.
rem Prefiere el entorno del proyecto, necesario para la voz neural local.
if exist "%~dp0backend\.venv\Scripts\python.exe" (
  set "ATLAS_PYTHON=%~dp0backend\.venv\Scripts\python.exe"
) else (
  set "ATLAS_PYTHON=python"
)
"%ATLAS_PYTHON%" "%~dp0scripts\start_atlas.py" %*
