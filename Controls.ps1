[CmdletBinding()]
param([ValidateSet('Menu','Status','Stop','Restart','Auto','Updates','Update','Force','Uninstall','Export')][string]$Mode = 'Menu')
$ErrorActionPreference = 'Stop'
$Host.UI.RawUI.WindowTitle = 'ROB RUN patch controls'
$root = [IO.Path]::GetFullPath($PSScriptRoot)
$appRoot = $root
if ((Split-Path $root -Leaf) -eq 'app') { $root = Split-Path $root -Parent }
$bootstrap = Join-Path $PSScriptRoot 'tools\Bootstrap.ps1'
if (-not (Test-Path -LiteralPath (Join-Path $appRoot 'SHA256SUMS.txt')) -and (Test-Path -LiteralPath $bootstrap)) {
    & $bootstrap -Mode $Mode
    exit $LASTEXITCODE
}
$patchPath = Join-Path $appRoot 'patch.py'
$runtimePath = Join-Path $appRoot 'runtime\python.exe'
function Get-PatchProcess {
    @(Get-CimInstance Win32_Process -Filter "Name = 'python.exe'" | Where-Object {
        $_.ExecutablePath -eq $runtimePath -and $_.CommandLine -like ('*' + $patchPath + '*') -and $_.CommandLine -notlike '*--guard*'
    })
}
function Set-Setting($name, $value) {
    $file = Join-Path $appRoot 'settings.json'
    $settings = [ordered]@{}
    if ((Test-Path -LiteralPath $file) -and (Get-Item -LiteralPath $file).Length -le 4096) {
        try { $old = Get-Content -LiteralPath $file -Raw | ConvertFrom-Json; foreach ($p in $old.PSObject.Properties) { $settings[$p.Name] = $p.Value } } catch { $settings = [ordered]@{} }
    }
    $settings[$name] = $value
    [IO.File]::WriteAllText($file, ($settings | ConvertTo-Json -Compress))
}
function Request-Stop {
    [IO.File]::WriteAllText((Join-Path $appRoot 'stop.request'),'stop')
    Write-Host 'Stop requested. Leave any relayed game location normally; the patch then exits.'
}
function Wait-ForStop {
    $deadline = (Get-Date).AddMinutes(5)
    while ((Get-PatchProcess).Count -gt 0) {
        if ((Get-Date) -gt $deadline) { throw 'Still running. Leave the location and retry, or choose emergency stop in CONTROLS.cmd.' }
        Start-Sleep -Milliseconds 500
    }
    # Wait for the cleanup guardian belonging to this exact extracted copy.
    do {
        $guard = @(Get-CimInstance Win32_Process -Filter "Name = 'python.exe'" | Where-Object { $_.ExecutablePath -eq $runtimePath -and $_.CommandLine -like ('*' + $patchPath + '*--guard*') })
        if ((Get-Date) -gt $deadline) { throw 'Cleanup is still running. Retry shortly.' }
        if ($guard.Count) { Start-Sleep -Milliseconds 500 }
    } while ($guard.Count)
}
try {
    if ($Mode -eq 'Menu') {
        Write-Host 'UNOFFICIAL PATCH - COULD GET YOU BANNED. NO SAFETY GUARANTEE.' -ForegroundColor Yellow
        Write-Host '1 Status   2 Safe stop   3 Restart helper   4 Automatic rearm on/off'
        Write-Host '5 Emergency stop (may disconnect game)   6 Uninstall   7 Export logs'
        Write-Host '8 Check for / install update   9 Update checks on/off   Enter Exit'
        $choice = Read-Host 'Choose'
        $Mode = switch ($choice) { '1' {'Status'} '2' {'Stop'} '3' {'Restart'} '4' {'Auto'} '5' {'Force'} '6' {'Uninstall'} '7' {'Export'} '8' {'Update'} '9' {'Updates'} default {exit 0} }
    }
    $admin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
    if (-not $admin -and $Mode -in @('Status','Restart','Force','Uninstall')) {
        $child = Start-Process powershell.exe -Verb RunAs -WindowStyle Normal -ArgumentList '-NoProfile','-ExecutionPolicy','Bypass','-File',('"' + $PSCommandPath + '"'),'-Mode',$Mode -Wait -PassThru
        exit $child.ExitCode
    }
    switch ($Mode) {
        'Export' { & $runtimePath $patchPath --export }
        'Status' {
            $running = Get-PatchProcess
            if ($running.Count) { Write-Host 'This copy is RUNNING.' } else { Write-Host 'This copy is STOPPED.' }
            $state = Join-Path $appRoot 'status.json'
            if (Test-Path -LiteralPath $state) { Write-Host ('Last status: ' + ((Get-Content -LiteralPath $state -Raw | ConvertFrom-Json).status)) }
            Write-Host 'No Windows startup task is installed. Auto rearm stays inside a running helper.'
        }
        'Stop' { Request-Stop }
        'Restart' {
            Request-Stop
            Wait-ForStop
            Write-Host 'Restarting the helper. Your game is not restarted.'
            Start-Process powershell.exe -WindowStyle Normal -ArgumentList '-NoProfile','-ExecutionPolicy','Bypass','-File',('"' + (Join-Path $appRoot 'Launch.ps1') + '"')
        }
        'Auto' {
            $answer = Read-Host 'Rearm automatically after leaving a repaired location? Y = on, N = stop after that location'
            if ($answer -notin @('Y','N')) { exit 0 }
            Set-Setting 'auto_rearm' ($answer -eq 'Y')
            Write-Host 'Saved. No game restarts and no Windows autostart are enabled.'
        }
        'Updates' {
            Write-Host 'When on, START asks GitHub (api.github.com, one anonymous request at most every 6 hours) whether a newer release exists. Nothing else is sent.'
            $answer = Read-Host 'Check for updates at start? Y = on, N = off'
            if ($answer -notin @('Y','N')) { exit 0 }
            Set-Setting 'check_updates' ($answer -eq 'Y')
            Write-Host 'Saved.'
        }
        'Update' { & (Join-Path $appRoot 'Update.ps1') -Mode Install }
        'Force' {
            Write-Host 'Emergency stop CAN DISCONNECT your relayed game session.' -ForegroundColor Red
            if ((Read-Host 'Type STOP to continue') -cne 'STOP') { exit 0 }
            Request-Stop
            foreach ($proc in (Get-PatchProcess)) { Stop-Process -Id $proc.ProcessId -Force }
            Wait-ForStop
            Write-Host 'Helper stopped. Its cleanup guardian has exited.'
        }
        'Uninstall' {
            Write-Host 'Removes this extracted patch copy and its local diagnostic files.'
            Write-Host 'Does not remove your game, Tailscale, or the shared Wintun driver.'
            if ((Read-Host 'Type UNINSTALL to continue') -cne 'UNINSTALL') { exit 0 }
            foreach ($directory in @($root,$appRoot,(Join-Path $appRoot 'runtime'),(Join-Path $appRoot 'logs'))) {
                if ((Test-Path -LiteralPath $directory) -and ((Get-Item -LiteralPath $directory -Force).Attributes -band [IO.FileAttributes]::ReparsePoint)) { throw 'Uninstall refuses linked directories. Stop the patch and review the folder manually.' }
            }
            Request-Stop
            Wait-ForStop
            $manifest = Join-Path $appRoot 'SHA256SUMS.txt'
            if (-not (Test-Path -LiteralPath $manifest)) { throw 'Release manifest missing. Patch stopped; remove its extracted folder manually.' }
            $owned = @('START.cmd','UNINSTALL.cmd','DEMO.cmd','app/README.txt','app/VERSION','app/Launch.ps1','app/Controls.ps1','app/Update.ps1','app/patch.py','app/transport.py','app/diagnostics.py','app/tracking.py','app/console.py','app/demo.py','app/LICENSE','app/THIRD-PARTY.md','app/WINTUN-LICENSE.txt','app/wintun.dll')
            $kept = 0
            foreach ($line in [IO.File]::ReadAllLines($manifest)) {
                if ($line -notmatch '^([a-f0-9]{64})  (.+)$') { throw 'Invalid manifest.' }
                $expected = $Matches[1]; $relative = $Matches[2]
                if ($relative -notin $owned -and $relative -notmatch '^app/runtime/[A-Za-z0-9_.-]+$') { throw 'Unexpected uninstall entry.' }
                $target = [IO.Path]::GetFullPath((Join-Path $root $relative))
                if (-not $target.StartsWith(($root.TrimEnd('\') + '\'),[StringComparison]::OrdinalIgnoreCase)) { throw 'Path outside patch folder.' }
                if (Test-Path -LiteralPath $target) {
                    if ((Get-FileHash -LiteralPath $target -Algorithm SHA256).Hash -eq $expected) { Remove-Item -LiteralPath $target -Force }
                    else { $kept++ }
                }
            }
            foreach ($relative in @('app\stop.request','app\status.json','app\settings.json','app\update-check.json','app\diagnostics-share.txt','app\logs\diagnostics.jsonl','app\logs\diagnostics.previous.jsonl','app\SHA256SUMS.txt')) {
                $target = Join-Path $root $relative
                if (Test-Path -LiteralPath $target -PathType Leaf) { Remove-Item -LiteralPath $target -Force }
            }
            foreach ($relative in @('app\runtime','app\logs','app')) {
                $target = Join-Path $root $relative
                if ((Test-Path -LiteralPath $target -PathType Container) -and -not (Get-ChildItem -LiteralPath $target -Force | Select-Object -First 1)) { Remove-Item -LiteralPath $target }
            }
            Write-Host "Uninstalled. $kept modified files preserved. You may remove the leftover extracted folder."
        }
    }
    [void](Read-Host 'Press Enter to close')
} catch {
    Write-Host $_.Exception.Message -ForegroundColor Red
    [void](Read-Host 'Press Enter to close')
    exit 1
}
