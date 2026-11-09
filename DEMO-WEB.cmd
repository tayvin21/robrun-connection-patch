@echo off
setlocal
set "app=%~dp0app"
if not exist "%app%\patch.py" set "app=%~dp0"
title ROB RUN patch - web demo
echo Scripted demo only. No game, no administrator rights, no network changes.
echo Opening http://127.0.0.1:38457/ in your browser. Press ENTER here to end the demo.
start "" "http://127.0.0.1:38457/"
"%app%\runtime\python.exe" "%app%\patch.py" --demo --view web
if errorlevel 1 pause
