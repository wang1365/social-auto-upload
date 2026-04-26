@echo off
TITLE Social Auto Upload 1.0
setlocal
set "ROOT_DIR=%~dp0"
set "VENV_PY=%ROOT_DIR%.venv\Scripts\python.exe"

ECHO ==================================================
ECHO  Starting Social Auto Upload 1.0 desktop client
ECHO ==================================================
ECHO.

if not exist "%VENV_PY%" (
  ECHO [ERROR] Missing virtual environment Python: %VENV_PY%
  ECHO Please run: uv venv .venv ^&^& uv pip install -r requirements.txt ^&^& uv pip install -e .
  goto :end
)

START "SAU Desktop" /D "%ROOT_DIR%" cmd /k ""%VENV_PY%" -m sau_desktop.main"

ECHO Desktop client launched.
timeout /t 3 /nobreak > nul

:end
endlocal
