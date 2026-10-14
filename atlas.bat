@echo off
rem Levanta todo ATLAS: backend, dashboard, movil y Mundo. Ctrl+C detiene todo.
rem Acepta las mismas opciones que scripts\start_atlas.py (ej: atlas.bat --desktop).
python "%~dp0scripts\start_atlas.py" %*
