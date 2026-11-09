@echo off
setlocal
set "app=%~dp0app"
if not exist "%app%\patch.py" set "app=%~dp0"
title ROB RUN patch - animated demo
echo Scripted demo only. No game, no administrator rights, no network changes.
echo Keys: 1 2 3 pick a server, ENTER or S ends the demo.
echo.
"%app%\runtime\python.exe" "%app%\patch.py" --demo
if errorlevel 1 pause
