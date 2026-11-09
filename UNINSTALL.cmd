@echo off
setlocal
cd /d "%~dp0"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0Controls.ps1" -Mode Uninstall
if errorlevel 1 pause
