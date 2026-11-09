[CmdletBinding()]
param([ValidateSet('Start','Menu','Status','Stop','Restart','Auto','Force','Uninstall','Export')][string]$Mode = 'Start', [switch]$PrepareOnly)
$ErrorActionPreference = 'Stop'
$version = '0.2.1'
$expectedHash = 'ea3c6b5bf3177ef9075eff3d6ea6916c1350d7cd0baadddfc45b8920cd6e0f61'
$sourceRoot = Split-Path $PSScriptRoot -Parent
$cache = Join-Path $sourceRoot ('.ready-to-run\' + $version)
$install = Join-Path $cache 'ROB-RUN-Connection-Patch'
$launcher = Join-Path $install 'app\Launch.ps1'
$prepared = Join-Path $cache 'prepared.txt'
try {
    if (Test-Path -LiteralPath (Join-Path $PSScriptRoot 'RELEASE-PAUSED.txt')) {
        throw 'Downloads are paused: Defender flagged the previous release. Do not override antivirus protection. See the repository notice.'
    }
    if (-not (Test-Path -LiteralPath $launcher) -or -not (Test-Path -LiteralPath $prepared)) {
        if ($Mode -ne 'Start' -and -not $PrepareOnly) { Write-Host 'This source copy has not installed the runnable patch. Nothing is running from it.'; exit 0 }
        Write-Host 'Preparing ROB RUN Connection Patch. Downloading the ready-to-run package from GitHub...'
        Write-Host 'No Python or Tailscale installation needed. This happens only on first launch.'
        [void][IO.Directory]::CreateDirectory($cache)
        $archive = Join-Path $cache 'package.zip'
        if (-not (Test-Path -LiteralPath $archive)) {
            [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
            Invoke-WebRequest -UseBasicParsing -Uri ('https://github.com/tayvin21/robrun-connection-patch/releases/download/v' + $version + '/ROB-RUN-Connection-Patch.zip') -OutFile $archive -TimeoutSec 120
        }
        if ((Get-Item -LiteralPath $archive).Length -gt 20MB -or (Get-FileHash -LiteralPath $archive -Algorithm SHA256).Hash -ne $expectedHash) {
            Remove-Item -LiteralPath $archive -Force
            throw 'Download verification failed. Nothing was started. Retry START.cmd.'
        }
        Add-Type -AssemblyName System.IO.Compression.FileSystem
        $zip = [IO.Compression.ZipFile]::OpenRead($archive)
        try {
            $prefix = [IO.Path]::GetFullPath($install).TrimEnd('\') + '\'
            $bytes = 0L
            if ($zip.Entries.Count -gt 200) { throw 'Unexpected archive entry count.' }
            foreach ($entry in $zip.Entries) {
                $target = [IO.Path]::GetFullPath((Join-Path $cache $entry.FullName))
                $bytes += $entry.Length
                if (-not $target.StartsWith($prefix,[StringComparison]::OrdinalIgnoreCase) -or $bytes -gt 100MB) { throw 'Unexpected archive contents.' }
            }
            # Only the pinned official archive reaches extraction. Never accepts user archives.
            foreach ($entry in $zip.Entries) {
                $target = [IO.Path]::GetFullPath((Join-Path $cache $entry.FullName))
                [void][IO.Directory]::CreateDirectory([IO.Path]::GetDirectoryName($target))
                [IO.Compression.ZipFileExtensions]::ExtractToFile($entry,$target,$true)
            }
        } finally { $zip.Dispose() }
        Remove-Item -LiteralPath $archive -Force
        [IO.File]::WriteAllText($prepared,$expectedHash)
        Write-Host ('Ready. Runnable folder: ' + $install)
    }
    if ($PrepareOnly) { exit 0 }
    if ($Mode -eq 'Start') { & $launcher }
    else { & (Join-Path $install 'app\Controls.ps1') -Mode $Mode }
    exit $LASTEXITCODE
} catch {
    Write-Host $_.Exception.Message -ForegroundColor Red
    Write-Host 'Direct download: https://github.com/tayvin21/robrun-connection-patch/releases/tag/v0.2.1'
    exit 1
}
