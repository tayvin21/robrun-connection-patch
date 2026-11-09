@echo off
setlocal
set "app=%~dp0app"
if not exist "%app%\patch.py" set "app=%~dp0"
if not exist "%app%\dashboard.json" (
  echo The patch is not running, so there is no status page. Start it with START.cmd first.
  pause
  exit /b 1
)
powershell.exe -NoProfile -Command "$u=(Get-Content -LiteralPath '%app%\dashboard.json' -Raw | ConvertFrom-Json).url; if ($u -match '^http://127\.0\.0\.1:\d+/$') { Start-Process $u } else { Write-Host 'Unexpected status address.' }"
