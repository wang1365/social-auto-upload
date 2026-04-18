@echo off
TITLE One-Click Starter for social-auto-upload
setlocal
set "ROOT_DIR=%~dp0"
set "VENV_PY=%ROOT_DIR%.venv\Scripts\python.exe"

ECHO ==================================================
ECHO  Starting social-auto-upload Servers...
ECHO ==================================================
ECHO.

ECHO [1/2] Starting Python Backend Server in a new window...
REM The START command launches a new process.
REM The first quoted string "SAU Backend" is the title of the new window.
REM cmd /k runs the command and keeps the window open to show logs.
if not exist "%VENV_PY%" (
  ECHO [ERROR] Missing virtual environment Python: %VENV_PY%
  ECHO Please run: uv venv .venv ^&^& uv pip install -r requirements.txt ^&^& uv pip install -e ".[web]"
  goto :end
)
START "SAU Backend" /D "%ROOT_DIR%" cmd /k ""%VENV_PY%" sau_backend.py"

ECHO [2/2] Starting Vue.js Frontend Server in another new window...
START "SAU Frontend" /D "%ROOT_DIR%sau_frontend" cmd /k "npm run dev -- --host 0.0.0.0"

ECHO.
ECHO ==================================================
ECHO  Done.
ECHO  Two new windows have been opened for the backend
ECHO  and frontend servers. You can monitor logs there.
ECHO ==================================================
ECHO.

ECHO This window will close in 10 seconds...
timeout /t 10 /nobreak > nul
:end
endlocal
