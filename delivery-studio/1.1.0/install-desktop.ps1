param(
    [Parameter(Mandatory = $true)][uri]$ManifestUrl,
    [Parameter(Mandatory = $true)][string]$InstallDir,
    [Parameter(Mandatory = $true)][string]$CacheDir
)
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
$studioInstallerSha = '8d6153371033aaf3e338baa4dcc2117982213270babdd51d353ce1d1aec21160'
$studioJoinSha = '61223acc63f9c1622db19448de3528d2529a2547d2f7cfd26436b49b9bc2699b'
if ($ManifestUrl.Scheme -ne 'https' -or $ManifestUrl.Host -ne 'raw.githubusercontent.com' -or $ManifestUrl.Port -ne 443 -or $ManifestUrl.AbsolutePath -notmatch '^/chw20071012-creator/trade-forecast/[a-f0-9]{40}/delivery-studio/1\.1\.0/parts-manifest\.json$' -or $ManifestUrl.Query -or $ManifestUrl.Fragment) {
    throw 'Use the exact commit-pinned manifest URL provided with this installer.'
}
if (-not [Environment]::Is64BitOperatingSystem) { throw 'Windows x64 is required.' }
$studioInstallPath = [IO.Path]::GetFullPath($InstallDir)
$studioCachePath = [IO.Path]::GetFullPath($CacheDir)
if ($studioInstallPath -notmatch '^[A-Za-z]:\\.+' -or $studioCachePath -notmatch '^[A-Za-z]:\\.+') {
    throw 'Use dedicated folders on a local drive, not a drive root or network path.'
}
if ($studioCachePath -eq $studioInstallPath -or $studioCachePath.StartsWith($studioInstallPath.TrimEnd('\') + '\', [StringComparison]::OrdinalIgnoreCase)) {
    throw 'Keep the download cache separate from the installation folder.'
}
New-Item -ItemType Directory -Force -Path $studioCachePath | Out-Null
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
$studioSavedProgress = $ProgressPreference
$ProgressPreference = 'SilentlyContinue'
function Get-StudioVerifiedFile {
    param([string]$Url, [string]$Destination, [string]$Sha256, [long]$Bytes = -1)
    if (Test-Path -LiteralPath $Destination) {
        $studioExistingSha = (Get-FileHash -LiteralPath $Destination -Algorithm SHA256).Hash.ToLowerInvariant()
        if ($studioExistingSha -eq $Sha256 -and ($Bytes -lt 0 -or (Get-Item -LiteralPath $Destination).Length -eq $Bytes)) { return }
        throw ('A different cached file already exists and was preserved: ' + $Destination)
    }
    $studioPartial = $Destination + '.' + [Guid]::NewGuid().ToString('N') + '.partial'
    try {
        Invoke-WebRequest -Uri $Url -OutFile $studioPartial -UseBasicParsing -TimeoutSec 600
        if ($Bytes -ge 0 -and (Get-Item -LiteralPath $studioPartial).Length -ne $Bytes) { throw 'Downloaded file size differs from the manifest.' }
        if ((Get-FileHash -LiteralPath $studioPartial -Algorithm SHA256).Hash.ToLowerInvariant() -ne $Sha256) { throw 'Downloaded file SHA256 differs from the manifest.' }
        [IO.File]::Move($studioPartial, $Destination)
    } finally {
        if (Test-Path -LiteralPath $studioPartial) { Remove-Item -LiteralPath $studioPartial -Force }
    }
}
try {
    $studioBaseUrl = $ManifestUrl.AbsoluteUri.Substring(0, $ManifestUrl.AbsoluteUri.LastIndexOf('/') + 1)
    $studioManifestText = (Invoke-WebRequest -Uri $ManifestUrl.AbsoluteUri -UseBasicParsing -TimeoutSec 60).Content
    $studioManifest = $studioManifestText | ConvertFrom-Json
    if ($studioManifest.version -ne '1.1.0' -or $studioManifest.installer_sha256 -ne $studioInstallerSha -or $studioManifest.installer_bytes -ne 654955996 -or @($studioManifest.parts).Count -ne 33) {
        throw 'This is not the expected Delivery Studio 1.1.0 package.'
    }
    $studioManifestPath = Join-Path $studioCachePath 'parts-manifest.json'
    if (Test-Path -LiteralPath $studioManifestPath) {
        $studioOldManifest = Get-Content -LiteralPath $studioManifestPath -Raw -Encoding UTF8 | ConvertFrom-Json
        if ($studioOldManifest.installer_sha256 -ne $studioInstallerSha) { throw 'An unrelated manifest already exists in the cache.' }
    }
    [IO.File]::WriteAllText($studioManifestPath, [string]$studioManifestText, (New-Object Text.UTF8Encoding($false)))
    $studioIndex = 0
    foreach ($studioPart in $studioManifest.parts) {
        $studioIndex++
        $studioExpectedName = 'delivery-studio-1.1.0-part-{0:d4}.zip' -f $studioIndex
        if ($studioPart.file -ne $studioExpectedName) { throw 'Unexpected part filename or order.' }
        Write-Host ('Downloading and verifying part {0}/33...' -f $studioIndex)
        Get-StudioVerifiedFile -Url ($studioBaseUrl + $studioExpectedName) -Destination (Join-Path $studioCachePath $studioExpectedName) -Sha256 $studioPart.archive_sha256 -Bytes $studioPart.archive_bytes
    }
    $studioJoin = Join-Path $studioCachePath 'join-install-parts.ps1'
    Get-StudioVerifiedFile -Url ($studioBaseUrl + 'join-install-parts.ps1') -Destination $studioJoin -Sha256 $studioJoinSha
    & $studioJoin -PartsFolder $studioCachePath -OutputFolder $studioCachePath | Out-Host
    $studioInstaller = Join-Path $studioCachePath $studioManifest.installer
    if ((Get-FileHash -LiteralPath $studioInstaller -Algorithm SHA256).Hash.ToLowerInvariant() -ne $studioInstallerSha) { throw 'Installer SHA256 check failed.' }
    Write-Host 'Installing the verified desktop application...'
    $studioSetup = Start-Process -FilePath $studioInstaller -ArgumentList @('/S', ('/D=' + $studioInstallPath)) -Wait -PassThru
    if ($studioSetup.ExitCode -ne 0) { throw ('Installer exited with code ' + $studioSetup.ExitCode + '. Preserve the cache and inspect the installation error.') }
    $studioApplicationLeaf = [string]$studioManifest.application
    if ([IO.Path]::GetFileName($studioApplicationLeaf) -ne $studioApplicationLeaf -or -not $studioApplicationLeaf.EndsWith('.exe')) { throw 'Unsafe application filename.' }
    $studioApplication = Join-Path (Join-Path $studioInstallPath 'app') $studioApplicationLeaf
    if (-not (Test-Path -LiteralPath $studioApplication)) { throw 'Installation finished without the expected desktop executable.' }
    Start-Process -FilePath $studioApplication -WorkingDirectory (Split-Path -Parent $studioApplication) | Out-Null
    Write-Output ('INSTALLED_APPLICATION=' + $studioApplication)
    Write-Output ('INSTALLATION_DATA=' + (Join-Path $studioInstallPath 'data'))
} finally {
    $ProgressPreference = $studioSavedProgress
}
