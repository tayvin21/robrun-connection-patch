<#
ROB RUN Hang Watcher

Reads the game's own text log (Player.log) and warns you within about 2 seconds when a server move
has been sent to a battle server that is not answering, instead of leaving you on
"...waiting for status information" for 60 seconds.

It does not open the game's process, read its memory, touch its files, or send or change any
network traffic. The optional -AutoRestart sends the game's window a normal close request (the same
thing as clicking X) and starts the game through Steam. It never force-kills the game.
#>
[CmdletBinding()]
param(
    [string]$LogPath = (Join-Path $env:USERPROFILE 'AppData\LocalLow\Kefir\ROB RUN\Player.log'),
    [double]$StallSeconds = 2,
    [switch]$AutoRestart,
    [int]$RestartAfterFailures = 1,
    [int]$MaxRestarts = 5,
    [int]$RestartCooldownSeconds = 120,
    [switch]$Quiet,
    [switch]$DryRun,
    [switch]$NoRelaunch,
    [switch]$TestAlert,
    [string]$ReplayFile,
    [string]$CsvPath,
    [string]$WindowTitle = 'ROB RUN',
    [string]$WindowClass = 'UnityWndClass',
    [int]$PollMs = 200
)

$ErrorActionPreference = 'Stop'
if (-not $CsvPath) { $CsvPath = Join-Path (Split-Path -Parent $MyInvocation.MyCommand.Path) 'moves.csv' }
$SteamAppId = 4262460

Add-Type @"
using System;
using System.Runtime.InteropServices;
public static class RobRunWatcherWin32 {
    [DllImport("user32.dll", CharSet = CharSet.Unicode, EntryPoint = "FindWindowW")]
    static extern IntPtr FindWindow(string windowClass, string title);
    [DllImport("user32.dll")] public static extern bool IsWindow(IntPtr handle);
    [DllImport("user32.dll")] static extern bool ShowWindow(IntPtr handle, int command);
    [DllImport("kernel32.dll")] static extern IntPtr GetConsoleWindow();
    public static void MinimizeConsole() { ShowWindow(GetConsoleWindow(), 6); }
    [DllImport("user32.dll")] static extern bool PostMessage(IntPtr handle, uint message, IntPtr w, IntPtr l);
    public static IntPtr Find(string windowClass, string title) {
        return FindWindow(string.IsNullOrEmpty(windowClass) ? null : windowClass, title);
    }
    public static bool RequestClose(IntPtr handle) {
        return PostMessage(handle, 0x0010, IntPtr.Zero, IntPtr.Zero);
    }
}
"@

$State = @{
    Move        = $null
    Tray        = $null
    Restarts    = 0
    LastRestart = $null
    Results     = New-Object System.Collections.ArrayList
}

function Write-Status([string]$Text, [string]$Color = 'Gray') {
    if ($ReplayFile) { return }
    Write-Host ("{0}  {1}" -f (Get-Date -Format 'HH:mm:ss'), $Text) -ForegroundColor $Color
}

function Get-ServerLabel([string]$HostName) {
    if (-not $HostName) { return 'unknown server' }
    return ($HostName -replace '^prod-game-[a-z]+-\d+-', '' -replace '\.rob-run\.kefir\.games\.?$', '')
}

function Send-Alert([string]$Title, [string]$Text) {
    Write-Status "$Title $Text" 'Yellow'
    if ($Quiet -or $ReplayFile) { return }
    try { [console]::Beep(880, 180); [console]::Beep(880, 180); [console]::Beep(660, 320) } catch { }
    try {
        if ($State.Tray) { $State.Tray.ShowBalloonTip(6000, $Title, $Text, [System.Windows.Forms.ToolTipIcon]::Warning) }
    } catch { }
}

function New-Move {
    return @{
        Server = $null; Ip = $null; Port = $null; Rtt = 0
        ConnectAt = $null; HandshakeOk = $false; Failures = 0
        Alerted = $false; AlertSeconds = $null; Restarted = $false
    }
}

function Complete-Move([string]$Result, [datetime]$Now) {
    $m = $State.Move
    $State.Move = $null
    if (-not $m -or -not $m.ConnectAt) { return }

    $seconds = [math]::Round(($Now - $m.ConnectAt).TotalSeconds, 1)
    [void]$State.Results.Add([pscustomobject]@{
        Time = $m.ConnectAt; Server = (Get-ServerLabel $m.Server); Result = $Result
        Failures = $m.Failures; Alerted = $m.Alerted; AlertSeconds = $m.AlertSeconds; Seconds = $seconds
    })

    if ($ReplayFile) { return }
    if ($Result -eq 'OK') {
        Write-Status ("Connected to {0}." -f (Get-ServerLabel $m.Server)) 'Green'
    } else {
        Write-Status ("{0}: {1} after {2}s, {3} failed attempts." -f $Result, (Get-ServerLabel $m.Server), $seconds, $m.Failures) 'Red'
    }
    if (-not $DryRun) {
        $row = '{0},{1},{2},{3},{4},{5},{6},{7}' -f $m.ConnectAt.ToUniversalTime().ToString('s'), (Get-ServerLabel $m.Server), $m.Ip, $m.Port, $m.Rtt, $Result, $m.Failures, $seconds
        try {
            if (-not (Test-Path -LiteralPath $CsvPath)) {
                Set-Content -LiteralPath $CsvPath -Value 'time_utc,server,ip,port,ping_ms,result,failed_attempts,seconds' -Encoding ASCII
            }
            Add-Content -LiteralPath $CsvPath -Value $row -Encoding ASCII
        } catch {
            Write-Status 'Could not write moves.csv. Warnings still work.' 'Yellow'
        }
    }
}

function Invoke-Restart([datetime]$Now) {
    $State.Move.Restarted = $true
    if ($ReplayFile) { return }

    if ($State.Restarts -ge $MaxRestarts) {
        Write-Status "Auto restart limit reached ($MaxRestarts). Not restarting again." 'Yellow'
        return
    }
    if ($State.LastRestart -and ($Now - $State.LastRestart).TotalSeconds -lt $RestartCooldownSeconds) {
        Write-Status 'Auto restart skipped: too soon after the last one.' 'Yellow'
        return
    }

    $window = [RobRunWatcherWin32]::Find($WindowClass, $WindowTitle)
    if ($window -eq [IntPtr]::Zero) {
        Send-Alert 'ROB RUN: restart skipped' 'Could not find the game window. Close it yourself.'
        return
    }
    if ($DryRun) {
        Write-Status 'Dry run: would ask the game window to close, then relaunch through Steam.' 'Cyan'
        return
    }

    Write-Status 'Asking the game window to close...' 'Cyan'
    [void][RobRunWatcherWin32]::RequestClose($window)
    $deadline = (Get-Date).AddSeconds(20)
    while ([RobRunWatcherWin32]::IsWindow($window) -and (Get-Date) -lt $deadline) { Start-Sleep -Milliseconds 250 }

    if ([RobRunWatcherWin32]::IsWindow($window)) {
        Send-Alert 'ROB RUN: restart stopped' 'The game did not close. Close it yourself.'
        return
    }

    $State.Restarts++
    $State.LastRestart = Get-Date
    if ($NoRelaunch) {
        Write-Status 'Game closed. Relaunch is turned off.' 'Cyan'
        return
    }
    Start-Sleep -Seconds 3
    Write-Status 'Starting the game through Steam. Press Play when it loads.' 'Cyan'
    Start-Process "steam://rungameid/$SteamAppId"
}

function Test-Stall([datetime]$Now) {
    $m = $State.Move
    if (-not $m -or -not $m.ConnectAt -or $m.HandshakeOk) { return }

    $limit = [math]::Max($StallSeconds, $m.Rtt * 10 / 1000.0)
    $elapsed = ($Now - $m.ConnectAt).TotalSeconds
    if (-not $m.Alerted -and $elapsed -ge $limit) {
        $m.Alerted = $true
        $m.AlertSeconds = [math]::Round($elapsed, 1)
        $action = if ($AutoRestart) { 'Restarting after the first failed attempt.' } else { 'Relaunch now, or wait for the 60 second kick.' }
        Send-Alert 'ROB RUN: dead server' ("{0} is not answering. {1}" -f (Get-ServerLabel $m.Server), $action)
    }
    if ($AutoRestart -and -not $m.Restarted -and $m.Failures -ge $RestartAfterFailures) {
        Invoke-Restart $Now
    }
}

function Read-LogLine([string]$Line, [datetime]$Now) {
    if ($Line.IndexOf('id=battle') -lt 0 -and $Line.IndexOf('NetworkStep') -lt 0) { return }

    $step = [regex]::Match($Line, 'NetworkStep - Changed on "(\w+)"')
    if ($step.Success) {
        if ($State.Move) { Complete-Move 'HANG' $Now }
        if ($step.Groups[1].Value -eq 'InBattle') { $State.Move = New-Move }
        return
    }

    $m = $State.Move
    if (-not $m) { return }

    $found = [regex]::Match($Line, 'GetAddress completed id=battle host=(\S+?)\.? dnsAddresses=\d+ addresses=([\d.]+)')
    if ($found.Success) {
        if (-not $m.Server) { $m.Server = $found.Groups[1].Value; $m.Ip = $found.Groups[2].Value }
        return
    }

    $started = [regex]::Match($Line, 'PeerConnect started id=battle address=([\d.]+):(\d+) rtt=(\d+)')
    if ($started.Success) {
        if (-not $m.ConnectAt) {
            $m.ConnectAt = $Now
            $m.Ip = $started.Groups[1].Value
            $m.Port = $started.Groups[2].Value
            $m.Rtt = [int]$started.Groups[3].Value
        }
        return
    }

    if ($Line -match 'PeerConnect complete id=battle') { $m.HandshakeOk = $true; return }
    if ($Line -match 'PeerConnect failed id=battle') { $m.Failures++; return }
    if ($Line -match 'ConnectUpdater\.Connect completed id=battle') { Complete-Move 'OK' $Now; return }
}

function Invoke-Replay {
    $now = [datetime]::MinValue
    foreach ($line in [IO.File]::ReadLines($ReplayFile, [Text.Encoding]::GetEncoding(28591))) {
        $stamp = [regex]::Match($line, '^\[(\d{4}-\d\d-\d\d \d\d:\d\d:\d\d\.\d+)\] \[\d+\]')
        if ($stamp.Success) {
            $now = [datetime]::Parse($stamp.Groups[1].Value)
            Test-Stall $now
            continue
        }
        Read-LogLine $line $now
    }
    if ($State.Move) { Complete-Move 'ABANDONED' $now }
    $State.Results
}

if ($ReplayFile) { Invoke-Replay; return }

Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing
if (-not $Quiet) {
    $State.Tray = New-Object System.Windows.Forms.NotifyIcon
    $State.Tray.Icon = [System.Drawing.SystemIcons]::Warning
    $State.Tray.Text = 'ROB RUN Hang Watcher'
    $State.Tray.Visible = $true
}

if ($TestAlert) {
    Send-Alert 'ROB RUN: test' 'This is what a dead server warning looks and sounds like.'
    Start-Sleep -Seconds 7
    if ($State.Tray) { $State.Tray.Dispose() }
    return
}

Write-Status 'ROB RUN Hang Watcher is running. Press Ctrl+C to stop.' 'Green'
if ($AutoRestart) { Write-Status 'Auto restart is ON.' 'Yellow' }
if (-not $Quiet -and -not $DryRun) {
    Write-Status 'This window will minimize itself. Leave it running while you play.'
    Start-Sleep -Seconds 3
    [RobRunWatcherWin32]::MinimizeConsole()
}

$encoding = [Text.Encoding]::GetEncoding(28591)
$position = 0L
if (Test-Path -LiteralPath $LogPath) { $position = (New-Object IO.FileInfo $LogPath).Length }
$partial = ''

try {
    while ($true) {
        if (Test-Path -LiteralPath $LogPath) {
            $stream = $null
            try {
                $stream = [IO.File]::Open($LogPath, [IO.FileMode]::Open, [IO.FileAccess]::Read, [IO.FileShare]'ReadWrite,Delete')
                if ($stream.Length -lt $position) {
                    if ($State.Move) { Complete-Move 'ABANDONED' (Get-Date) }
                    Write-Status 'Game restarted, following the new log.'
                    $position = 0L
                    $partial = ''
                }
                if ($stream.Length -gt $position) {
                    [void]$stream.Seek($position, [IO.SeekOrigin]::Begin)
                    $buffer = New-Object byte[] ([math]::Min($stream.Length - $position, 1048576))
                    $count = $stream.Read($buffer, 0, $buffer.Length)
                    $position += $count
                    $lines = ($partial + $encoding.GetString($buffer, 0, $count)) -split "`n"
                    $partial = $lines[-1]
                    if ($lines.Count -gt 1) {
                        $now = Get-Date
                        foreach ($line in $lines[0..($lines.Count - 2)]) { Read-LogLine $line.TrimEnd("`r") $now }
                    }
                }
            } catch [IO.IOException] {
                # The game may hold the file briefly while rotating it. Try again on the next poll.
            } finally {
                if ($stream) { $stream.Dispose() }
            }
        }
        Test-Stall (Get-Date)
        Start-Sleep -Milliseconds $PollMs
    }
} finally {
    if ($State.Tray) { $State.Tray.Dispose() }
    $hangs = @($State.Results | Where-Object { $_.Result -eq 'HANG' }).Count
    Write-Status ("Stopped. Moves seen: {0}, hangs: {1}." -f $State.Results.Count, $hangs)
}
