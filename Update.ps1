[CmdletBinding()]
param(
    [ValidateSet('Check', 'Install')][string]$Mode = 'Check',
    [switch]$Quiet,
    [switch]$Force,
    # Testing hooks. They are only reachable by whoever runs this script locally.
    [string]$FeedFile,
    [string]$LocalZip
)
$ErrorActionPreference = 'Stop'
$Repo = 'tayvin21/robrun-connection-patch'
$AssetName = 'ROB-RUN-Connection-Patch.zip'
$DownloadPrefix = "https://github.com/$Repo/releases/download/"
$MaxZipBytes = 40MB
$MaxUnpackedBytes = 100MB
$CacheHours = 6
$appRoot = [IO.Path]::GetFullPath($PSScriptRoot)
$installRoot = if ((Split-Path $appRoot -Leaf) -eq 'app') { Split-Path $appRoot -Parent } else { $appRoot }

function Write-Note($text, $color) {
    if (-not $Quiet) { if ($color) { Write-Host $text -ForegroundColor $color } else { Write-Host $text } }
}

function Get-Setting($name, $default) {
    try {
        $file = Join-Path $appRoot 'settings.json'
        if (-not (Test-Path -LiteralPath $file)) { return $default }
        if ((Get-Item -LiteralPath $file).Length -gt 4096) { return $default }
        $value = (Get-Content -LiteralPath $file -Raw | ConvertFrom-Json).$name
        if ($value -is [bool]) { return $value }
    } catch { }
    return $default
}

function Get-InstalledVersion {
    $file = Join-Path $appRoot 'VERSION'
    if (-not (Test-Path -LiteralPath $file)) { throw 'This copy has no VERSION file.' }
    $text = (Get-Content -LiteralPath $file -Raw).Trim()
    if ($text -notmatch '^\d{1,3}\.\d{1,3}\.\d{1,4}$') { throw 'This copy has an unreadable VERSION file.' }
    return [version]$text
}

function ConvertTo-Version($tag) {
    if ($tag -notmatch '^v(\d{1,3}\.\d{1,3}\.\d{1,4})$') { return $null }
    return [version]$Matches[1]
}

function Get-Releases {
    if ($FeedFile) { return @(Get-Content -LiteralPath $FeedFile -Raw | ConvertFrom-Json) }
    [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
    $headers = @{ 'User-Agent' = 'rob-run-connection-patch-updater'; 'Accept' = 'application/vnd.github+json' }
    return @(Invoke-RestMethod -UseBasicParsing -Uri "https://api.github.com/repos/$Repo/releases?per_page=10" -Headers $headers -TimeoutSec 8)
}

function Find-Latest($releases) {
    $best = $null
    foreach ($release in $releases) {
        if ($release.draft) { continue }
        $version = ConvertTo-Version ([string]$release.tag_name)
        if (-not $version) { continue }
        $asset = @($release.assets | Where-Object { $_.name -eq $AssetName }) | Select-Object -First 1
        if (-not $asset) { continue }
        if ($best -and $version -le $best.Version) { continue }
        $digest = ''
        if ($asset.digest -match '^sha256:([a-fA-F0-9]{64})$') { $digest = $Matches[1].ToLowerInvariant() }
        elseif ([string]$release.body -match "SHA-256 of $([regex]::Escape($AssetName)):\s*([a-fA-F0-9]{64})") { $digest = $Matches[1].ToLowerInvariant() }
        $best = [pscustomobject]@{
            Version = $version; Tag = [string]$release.tag_name; Url = [string]$asset.browser_download_url
            Size = [int64]$asset.size; Digest = $digest; Page = [string]$release.html_url; Notes = [string]$release.body
        }
    }
    return $best
}

function Get-UpdateInfo {
    $current = Get-InstalledVersion
    $cache = Join-Path $appRoot 'update-check.json'
    $latest = $null
    if (-not $Force -and -not $FeedFile -and (Test-Path -LiteralPath $cache) -and (Get-Item -LiteralPath $cache).Length -lt 4096) {
        try {
            $saved = Get-Content -LiteralPath $cache -Raw | ConvertFrom-Json
            if (([datetime]::UtcNow - [datetime]::Parse($saved.checked_utc).ToUniversalTime()).TotalHours -lt $CacheHours -and $saved.current -eq $current.ToString()) {
                $v = ConvertTo-Version ('v' + $saved.latest)
                if ($v) { return [pscustomobject]@{ Current = $current; Latest = $v; Newer = ($v -gt $current); Release = $null } }
            }
        } catch { }
    }
    $latest = Find-Latest (Get-Releases)
    if (-not $latest) { return $null }
    if (-not $FeedFile) {
        try { [IO.File]::WriteAllText($cache, (@{ checked_utc = [datetime]::UtcNow.ToString('o'); current = $current.ToString(); latest = $latest.Version.ToString() } | ConvertTo-Json -Compress)) } catch { }
    }
    return [pscustomobject]@{ Current = $current; Latest = $latest.Version; Newer = ($latest.Version -gt $current); Release = $latest }
}

function Test-ZipLayout($zip, $stagingRoot) {
    if ($zip.Entries.Count -gt 200) { throw 'Unexpected archive entry count.' }
    $prefix = [IO.Path]::GetFullPath($stagingRoot).TrimEnd('\') + '\'
    $bytes = 0L
    foreach ($entry in $zip.Entries) {
        $target = [IO.Path]::GetFullPath((Join-Path $stagingRoot $entry.FullName))
        $bytes += $entry.Length
        if (-not $target.StartsWith($prefix, [StringComparison]::OrdinalIgnoreCase) -or $bytes -gt $MaxUnpackedBytes) { throw 'Unexpected archive contents.' }
        if (-not $entry.FullName.StartsWith('ROB-RUN-Connection-Patch/')) { throw 'Unexpected archive layout.' }
    }
}

function Install-Update($info) {
    $release = $info.Release
    if (-not $release) { $release = Find-Latest (Get-Releases) }
    if (-not $release) { throw 'No release found.' }
    if ($release.Version -le $info.Current) { Write-Note "Already up to date (v$($info.Current))." 'Green'; return }
    if (-not $release.Url.StartsWith($DownloadPrefix) -and -not $LocalZip) { throw 'Refusing a download address outside this project.' }
    if ($release.Size -le 0 -or $release.Size -gt $MaxZipBytes) { throw 'Unexpected download size.' }
    if (-not $release.Digest) { throw 'This release publishes no SHA-256, so it cannot be verified. Nothing was downloaded.' }
    $target = Join-Path (Split-Path $installRoot -Parent) ("ROB-RUN-Connection-Patch-v" + $release.Version)
    if (Test-Path -LiteralPath $target) { throw "$target already exists. Remove or rename it first." }
    Write-Host ''
    Write-Host "Update: v$($info.Current)  ->  v$($release.Version)  ($([math]::Round($release.Size / 1MB, 1)) MB)" -ForegroundColor Cyan
    Write-Host "Release page: $($release.Page)"
    Write-Host "SHA-256:      $($release.Digest)"
    $notes = ($release.Notes -split "`n" | Where-Object { $_.Trim() } | Select-Object -First 4) -join "`n"
    if ($notes) { Write-Host $notes }
    Write-Host ''
    Write-Host "It installs into a NEW folder next to this one:  $target"
    Write-Host 'Your current copy is not touched. The download is verified against the published SHA-256 before anything is unpacked.'
    if ((Read-Host 'Download and unpack it? Y/N') -ne 'Y') { Write-Host 'Cancelled.'; return }
    $work = Join-Path ([IO.Path]::GetTempPath()) ('robrun-update-' + [guid]::NewGuid().ToString('N'))
    [void][IO.Directory]::CreateDirectory($work)
    try {
        $archive = Join-Path $work $AssetName
        if ($LocalZip) { Copy-Item -LiteralPath $LocalZip -Destination $archive }
        else {
            [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
            Invoke-WebRequest -UseBasicParsing -Uri $release.Url -OutFile $archive -TimeoutSec 120 -Headers @{ 'User-Agent' = 'rob-run-connection-patch-updater' }
        }
        if ((Get-Item -LiteralPath $archive).Length -gt $MaxZipBytes) { throw 'Download is larger than expected.' }
        if ((Get-FileHash -LiteralPath $archive -Algorithm SHA256).Hash.ToLowerInvariant() -ne $release.Digest) { throw 'Download does not match the published SHA-256. Nothing was unpacked.' }
        Write-Host 'Download verified.' -ForegroundColor Green
        Add-Type -AssemblyName System.IO.Compression.FileSystem
        $staging = Join-Path $work 'staging'
        [void][IO.Directory]::CreateDirectory($staging)
        $zip = [IO.Compression.ZipFile]::OpenRead($archive)
        try {
            Test-ZipLayout $zip $staging
            foreach ($entry in $zip.Entries) {
                $path = [IO.Path]::GetFullPath((Join-Path $staging $entry.FullName))
                if ($entry.FullName.EndsWith('/')) { [void][IO.Directory]::CreateDirectory($path); continue }
                [void][IO.Directory]::CreateDirectory([IO.Path]::GetDirectoryName($path))
                [IO.Compression.ZipFileExtensions]::ExtractToFile($entry, $path, $true)
            }
        } finally { $zip.Dispose() }
        $unpacked = Join-Path $staging 'ROB-RUN-Connection-Patch'
        $newApp = Join-Path $unpacked 'app'
        $versionFile = Join-Path $newApp 'VERSION'
        if (-not (Test-Path -LiteralPath $versionFile) -or (Get-Content -LiteralPath $versionFile -Raw).Trim() -ne $release.Version.ToString()) { throw 'The package version does not match its release tag.' }
        $manifest = Join-Path $newApp 'SHA256SUMS.txt'
        $prefix = [IO.Path]::GetFullPath($unpacked).TrimEnd('\') + '\'
        $count = 0
        foreach ($line in [IO.File]::ReadAllLines($manifest)) {
            if ($line -notmatch '^([a-f0-9]{64})  (.+)$') { throw 'Invalid integrity manifest in the package.' }
            $file = [IO.Path]::GetFullPath((Join-Path $unpacked $Matches[2]))
            if (-not $file.StartsWith($prefix, [StringComparison]::OrdinalIgnoreCase)) { throw 'Invalid manifest path.' }
            if ((Get-FileHash -LiteralPath $file -Algorithm SHA256).Hash.ToLowerInvariant() -ne $Matches[1]) { throw 'Package integrity check failed.' }
            $count++
        }
        $settings = Join-Path $appRoot 'settings.json'
        if ((Test-Path -LiteralPath $settings) -and (Get-Item -LiteralPath $settings).Length -le 4096) {
            try { [void](Get-Content -LiteralPath $settings -Raw | ConvertFrom-Json); Copy-Item -LiteralPath $settings -Destination (Join-Path $newApp 'settings.json') } catch { }
        }
        Move-Item -LiteralPath $unpacked -Destination $target
        Write-Host "Installed v$($release.Version) ($count files verified):" -ForegroundColor Green
        Write-Host "  $target"
        Write-Host 'Next: leave any relayed game location, stop this window (ENTER), then run START.cmd in the new folder.'
        Write-Host 'Delete the old folder whenever you like (its UNINSTALL.cmd removes it cleanly).'
    } finally {
        Remove-Item -LiteralPath $work -Recurse -Force -ErrorAction SilentlyContinue
    }
}

try {
    if ($Mode -eq 'Check') {
        if (-not $FeedFile -and -not (Get-Setting 'check_updates' $true)) { return }
        $info = Get-UpdateInfo
        if ($info) {
            if ($info.Newer) { Write-Note "Update available: v$($info.Latest) (this is v$($info.Current))." 'Cyan' }
            else { Write-Note "Up to date (v$($info.Current))." 'Green' }
            $info
        }
        return
    }
    $Force = $true
    $info = Get-UpdateInfo
    if (-not $info) { throw 'No release information available.' }
    Install-Update $info
} catch {
    if ($Mode -eq 'Install') { Write-Host $_.Exception.Message -ForegroundColor Red; exit 1 }
    Write-Note 'Could not check for updates (offline or rate limited).' $null
}
