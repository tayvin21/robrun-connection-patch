@echo off
setlocal
set "tool=%~dp0app\Controls.ps1"
if not exist "%tool%" set "tool=%~dp0Controls.ps1"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%tool%" -Mode Uninstall
if errorlevel 1 pause
