@echo off
setlocal
set "tool=%~dp0app\Launch.ps1"
if not exist "%tool%" set "tool=%~dp0Launch.ps1"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%tool%"
if errorlevel 1 pause
