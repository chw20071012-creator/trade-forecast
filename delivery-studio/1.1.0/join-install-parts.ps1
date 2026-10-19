param(
    [Parameter(Mandatory = $true)][string]$PartsFolder,
    [string]$OutputFolder
)
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
$expectedSha = '8d6153371033aaf3e338baa4dcc2117982213270babdd51d353ce1d1aec21160'
$expectedBytes = 654955996L
$partsRoot = (Resolve-Path -LiteralPath $PartsFolder).Path
if (-not $OutputFolder) { $OutputFolder = $partsRoot }
$manifestPath = Join-Path $partsRoot 'parts-manifest.json'
$manifest = Get-Content -LiteralPath $manifestPath -Raw -Encoding UTF8 | ConvertFrom-Json
if ($manifest.format -ne 1 -or $manifest.version -ne '1.1.0' -or $manifest.installer_sha256 -ne $expectedSha -or $manifest.installer_bytes -ne $expectedBytes) {
    throw 'The manifest does not describe the expected installer.'
}
if (@($manifest.parts).Count -ne 33 -or $manifest.part_count -ne 33) {
    throw 'Expected exactly 33 archive parts.'
}
$leaf = [string]$manifest.installer
if ([IO.Path]::GetFileName($leaf) -ne $leaf -or -not $leaf.EndsWith('.exe')) {
    throw 'Unsafe installer filename.'
}
[IO.Directory]::CreateDirectory($OutputFolder) | Out-Null
$outputRoot = (Resolve-Path -LiteralPath $OutputFolder).Path
$destination = Join-Path $outputRoot $leaf
if (Test-Path -LiteralPath $destination) {
    if ((Get-FileHash -LiteralPath $destination -Algorithm SHA256).Hash.ToLowerInvariant() -eq $expectedSha) {
        Write-Output ('VERIFIED_INSTALLER=' + $destination)
        return
    }
    throw 'An unrelated file already exists at the output path; it will not be replaced.'
}
Add-Type -AssemblyName System.IO.Compression.FileSystem
$temporary = Join-Path $outputRoot ('delivery-installer-' + [Guid]::NewGuid().ToString('N') + '.partial')
$target = $null
try {
    $target = [IO.File]::Open($temporary, [IO.FileMode]::CreateNew, [IO.FileAccess]::Write, [IO.FileShare]::None)
    $index = 0
    foreach ($part in $manifest.parts) {
        $index++
        $expectedName = 'delivery-studio-1.1.0-part-{0:d4}.zip' -f $index
        $expectedMember = 'payload.part{0:d4}' -f $index
        if ($part.file -ne $expectedName -or $part.member -ne $expectedMember) { throw 'Invalid part order or filename.' }
        $archivePath = Join-Path $partsRoot $expectedName
        if ((Get-Item -LiteralPath $archivePath).Length -ne $part.archive_bytes) { throw ('Incorrect size: ' + $expectedName) }
        if ((Get-FileHash -LiteralPath $archivePath -Algorithm SHA256).Hash.ToLowerInvariant() -ne $part.archive_sha256) { throw ('Incorrect SHA256: ' + $expectedName) }
        $archive = [IO.Compression.ZipFile]::OpenRead($archivePath)
        try {
            if ($archive.Entries.Count -ne 1) { throw 'Unexpected archive contents.' }
            $entry = $archive.Entries[0]
            if ($entry.FullName -ne $expectedMember -or $entry.Length -ne $part.bytes) { throw 'Unexpected archive member or size.' }
            $source = $entry.Open()
            try { $source.CopyTo($target) } finally { $source.Dispose() }
        } finally { $archive.Dispose() }
        Write-Output ('Verified part {0}/33' -f $index)
    }
    $target.Dispose()
    $target = $null
    if ((Get-Item -LiteralPath $temporary).Length -ne $expectedBytes) { throw 'Reassembled installer size does not match.' }
    if ((Get-FileHash -LiteralPath $temporary -Algorithm SHA256).Hash.ToLowerInvariant() -ne $expectedSha) { throw 'Reassembled installer SHA256 does not match.' }
    [IO.File]::Move($temporary, $destination)
    Write-Output ('VERIFIED_INSTALLER=' + $destination)
} finally {
    if ($null -ne $target) { $target.Dispose() }
    if (Test-Path -LiteralPath $temporary) { Remove-Item -LiteralPath $temporary -Force }
}
