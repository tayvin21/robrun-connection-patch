[CmdletBinding()]
param([switch]$Elevated, [switch]$NoLogs)
$ErrorActionPreference = 'Stop'
$installRoot = $PSScriptRoot
if ((Split-Path $PSScriptRoot -Leaf) -eq 'app') { $installRoot = Split-Path $PSScriptRoot -Parent }
$manifest = Join-Path $PSScriptRoot 'SHA256SUMS.txt'
$bootstrap = Join-Path $PSScriptRoot 'tools\Bootstrap.ps1'
if (-not (Test-Path -LiteralPath $manifest) -and (Test-Path -LiteralPath $bootstrap)) {
    & $bootstrap -Mode Start
    exit $LASTEXITCODE
}
$Host.UI.RawUI.WindowTitle = 'ROB RUN - Unofficial Connection Patch'
try {
    Write-Host ''
    Write-Host 'UNOFFICIAL EXPERIMENTAL PATCH' -ForegroundColor Yellow
    Write-Host 'NOT APPROVED BY KEFIR OR EASY ANTI-CHEAT.' -ForegroundColor Yellow
    Write-Host 'THIS COULD GET YOU BANNED. ACCOUNT SAFETY IS UNKNOWN.' -ForegroundColor Red
    Write-Host 'USE AT YOUR OWN RISK. May fail or cause disconnects.' -ForegroundColor Red
    Write-Host 'Requires administrator access; changes network routing.'
    Write-Host 'No game-file/memory edits. No automatic uploads.'
    Write-Host 'Developed with AI assistance; may contain mistakes.'
    Write-Host ''
    if (-not $Elevated) {
        Write-Host 'By choosing R or N, you acknowledge the ban/disconnection risks above.'
        Write-Host 'No safety, reliability or anti-cheat compatibility is promised.'
        Write-Host 'You choose to use this at your own risk. Non-excludable legal rights remain.'
        Write-Host ''
        Write-Host 'R = accept risk and run (small local diagnostic logs ON)'
        Write-Host 'N = accept risk and run without logs'
        Write-Host 'S = safe stop    O = options / export logs    U = uninstall'
        Write-Host 'Anything else = cancel'
        $answer = Read-Host 'Choose'
        $controlMode = switch ($answer) { 'S' {'Stop'} 'O' {'Menu'} 'U' {'Uninstall'} default {$null} }
        if ($controlMode) { & (Join-Path $PSScriptRoot 'Controls.ps1') -Mode $controlMode; exit $LASTEXITCODE }
        if ($answer -notin @('R','N')) { exit 0 }
        $NoLogs = $answer -eq 'N'
    }
    if (-not (Test-Path -LiteralPath $manifest)) { throw 'Release files missing. Download the release ZIP and extract it fully.' }
    $rootPrefix = [IO.Path]::GetFullPath($installRoot).TrimEnd('\') + '\'
    foreach ($line in [IO.File]::ReadAllLines($manifest)) {
        if ($line -notmatch '^([a-f0-9]{64})  (.+)$') { throw 'Invalid integrity manifest.' }
        $expectedHash = $Matches[1]
        $full = [IO.Path]::GetFullPath((Join-Path $installRoot $Matches[2]))
        if (-not $full.StartsWith($rootPrefix,[StringComparison]::OrdinalIgnoreCase)) { throw 'Invalid manifest path.' }
        if ((Get-FileHash -LiteralPath $full -Algorithm SHA256).Hash -ne $expectedHash) { throw 'Release integrity check failed. Re-download from the official repository release.' }
    }
    foreach ($entry in @(@('wintun.dll','WireGuard LLC'), @('runtime\python.exe','Python Software Foundation'), @('runtime\python314.dll','Python Software Foundation'))) {
        $signature = Get-AuthenticodeSignature -FilePath (Join-Path $PSScriptRoot $entry[0])
        if ($signature.Status -ne 'Valid' -or $signature.SignerCertificate.Subject -notlike ('*' + $entry[1] + '*')) {
            throw ('Trusted signature check failed for ' + $entry[0] + '. Do not disable security software.')
        }
    }
    $isAdmin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
    if (-not $isAdmin) {
        $arguments = @('-NoProfile','-ExecutionPolicy','Bypass','-File',('"' + $PSCommandPath + '"'),'-Elevated')
        if ($NoLogs) { $arguments += '-NoLogs' }
        # Visible: this is the status window the user explicitly launches.
        $child = Start-Process powershell.exe -Verb RunAs -WindowStyle Normal -ArgumentList $arguments -Wait -PassThru
        exit $child.ExitCode
    }
    $patchArguments = @((Join-Path $PSScriptRoot 'patch.py'),'--accept-risk')
    if ($NoLogs) { $patchArguments += '--no-logs' }
    $stopRequest = Join-Path $PSScriptRoot 'stop.request'
    if (Test-Path -LiteralPath $stopRequest) { Remove-Item -LiteralPath $stopRequest }
    & (Join-Path $PSScriptRoot 'runtime\python.exe') @patchArguments
    $resultCode = $LASTEXITCODE
    [void](Read-Host 'Press Enter to close')
    exit $resultCode
} catch {
    Write-Host $_.Exception.Message -ForegroundColor Red
    exit 1
}
