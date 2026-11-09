@echo off
title ROB RUN Hang Watcher
rem For automatic restarts: Start.bat -AutoRestart
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0RobRunHangWatcher.ps1" %*
if errorlevel 1 (
    echo.
    echo The watcher stopped with an error. See the message above.
    pause
)
