@echo off
chcp 65001 >nul
setlocal
title 拾光分发 2.0
set "SAU_ROOT=%~dp0"
set "SAU_PYTHON=%SAU_ROOT%.venv\Scripts\python.exe"
if not exist "%SAU_PYTHON%" (
  echo 未找到 Python 运行环境，请先按 docs\web-2.0.md 完成安装。
  pause
  exit /b 1
)
if not exist "%SAU_ROOT%sau_web\static\index.html" (
  echo 请先构建 Web 界面：powershell -ExecutionPolicy Bypass -File tools\build_web.ps1
  pause
  exit /b 1
)
cd /d "%SAU_ROOT%"
"%SAU_PYTHON%" -m sau_web.launcher
if errorlevel 1 pause
endlocal
