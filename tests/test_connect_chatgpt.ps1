param([string]$PackagePath)
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$repo = Split-Path $PSScriptRoot -Parent
$script:checks = 0
function Assert-True([bool]$Value, [string]$Message) {
    if (-not $Value) { throw "FAIL: $Message" }
    $script:checks++
}
function Assert-Throws([scriptblock]$Action, [string]$Expected) {
    $caught = $false
    try { & $Action } catch {
        $caught = $true
        Assert-True ($_.Exception.Message -like "*$Expected*") ('Unexpected error: ' + $_.Exception.Message)
    }
    Assert-True $caught "Expected error: $Expected"
}
$source = Join-Path $repo 'scripts/connect-chatgpt.ps1'
$tokens = $null; $errors = $null
$ast = [Management.Automation.Language.Parser]::ParseFile($source, [ref]$tokens, [ref]$errors)
Assert-True ($errors.Count -eq 0) 'Connection script syntax'
foreach ($fn in $ast.FindAll({param($node) $node -is [Management.Automation.Language.FunctionDefinitionAst]}, $false)) {
    Invoke-Expression $fn.Extent.Text
}
$temp = Join-Path ([IO.Path]::GetTempPath()) ('trade-connect-tests-' + [Guid]::NewGuid().ToString('N'))
$null = New-Item -ItemType Directory -Path $temp
try {
    Assert-True ($null -eq (Get-TradeTunnelUrl $null)) 'Null log'
    Assert-True ($null -eq (Get-TradeTunnelUrl '')) 'Empty log'
    Assert-True ($null -eq (Get-TradeTunnelUrl " `r`n")) 'Whitespace log'
    Assert-True ($null -eq (Get-TradeTunnelUrl 'Starting connection...')) 'No URL yet'
    Assert-True ((Get-TradeTunnelUrl 'URL: https://one-two.trycloudflare.com |') -eq 'https://one-two.trycloudflare.com') 'Extract HTTPS URL'
    Assert-True ((Get-TradeTunnelUrl "https://old.trycloudflare.com`nhttps://new.trycloudflare.com") -eq 'https://new.trycloudflare.com') 'Use latest URL'
    $script:log = Join-Path $temp 'tunnel.log'
    [IO.File]::WriteAllText($script:log, '')
    Assert-True ($null -eq (Get-Content -LiteralPath $script:log -Raw)) 'Reproduce actual empty Get-Content result'
    $process = [pscustomobject]@{HasExited=$false; ExitCode=7}
    $process | Add-Member ScriptMethod Refresh {}
    $script:ticks=0; $script:writeAfter=2
    function Start-Sleep { param([int]$Seconds)
        $script:ticks++
        if ($script:ticks -eq $script:writeAfter) {
            [IO.File]::WriteAllText($script:log, 'https://ready-now.trycloudflare.com')
        }
    }
    $url = Wait-TradeTunnelUrl -LogPath $script:log -Process $process -Attempts 4
    Assert-True ($url -eq 'https://ready-now.trycloudflare.com') 'Wait through empty log until URL appears'
    Assert-True ($script:ticks -eq 2) 'Wait did not crash or return early'
    $process.HasExited=$true
    Assert-Throws { Wait-TradeTunnelUrl -LogPath $script:log -Process $process -Attempts 2 } 'exited'
    $process.HasExited=$false
    [IO.File]::WriteAllText($script:log, '')
    $script:ticks=0; $script:writeAfter=100
    Assert-Throws { Wait-TradeTunnelUrl -LogPath $script:log -Process $process -Attempts 3 } 'No HTTPS address'
    Assert-True ($script:ticks -eq 3) 'Timeout is bounded'
    Remove-Item -LiteralPath $script:log
    Assert-Throws { Wait-TradeTunnelUrl -LogPath $script:log -Process $process -Attempts 1 } 'No HTTPS address'
    $hashFile=Join-Path $temp 'hash.txt'
    [IO.File]::WriteAllText($hashFile, 'abc', (New-Object Text.UTF8Encoding($false)))
    Assert-True ((Get-TradeSha256 $hashFile) -eq 'ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad') 'SHA256 without module loading'
    Remove-Item -LiteralPath $hashFile
    $mine=Get-Process -Id $PID
    $recordPath=Join-Path $temp 'process.json'
    $record=@{pid=$PID; start_time_utc=$mine.StartTime.ToUniversalTime().ToString('o'); executable=$mine.Path; root='test-root'; role='tunnel'; port=8765}
    $record | ConvertTo-Json | Set-Content -LiteralPath $recordPath -Encoding UTF8
    $reused=Get-TradeExistingTunnel -RecordPath $recordPath -RootPath 'test-root' -Executable $mine.Path -ExpectedPort 8765
    Assert-True ($reused.Id -eq $PID) 'Reuse exact running process without CIM'
    Assert-Throws { Get-TradeExistingTunnel -RecordPath $recordPath -RootPath 'other' -Executable $mine.Path -ExpectedPort 8765 } 'another folder or port'
    Assert-Throws { Get-TradeExistingTunnel -RecordPath $recordPath -RootPath 'test-root' -Executable $mine.Path -ExpectedPort 9999 } 'another folder or port'
    Assert-Throws { Get-TradeExistingTunnel -RecordPath $recordPath -RootPath 'test-root' -Executable 'other.exe' -ExpectedPort 8765 } 'identity changed'
    $record.start_time_utc='2000-01-01T00:00:00Z'
    $record | ConvertTo-Json | Set-Content -LiteralPath $recordPath -Encoding UTF8
    Assert-Throws { Get-TradeExistingTunnel -RecordPath $recordPath -RootPath 'test-root' -Executable $mine.Path -ExpectedPort 8765 } 'identity changed'
    $record.pid=2147483647
    $record | ConvertTo-Json | Set-Content -LiteralPath $recordPath -Encoding UTF8
    Assert-True ($null -eq (Get-TradeExistingTunnel -RecordPath $recordPath -RootPath 'test-root' -Executable $mine.Path -ExpectedPort 8765)) 'Dead process may be restarted'

    if ($PackagePath) {
        Add-Type -AssemblyName System.IO.Compression.FileSystem
        $expanded=Join-Path $temp 'patch'
        [IO.Compression.ZipFile]::ExtractToDirectory([IO.Path]::GetFullPath($PackagePath), $expanded)
        $patchRoot=Join-Path $expanded 'TradeAgent-ChatGPT-Fix'
        Assert-True ((Get-TradeSha256 (Join-Path $patchRoot 'connect-chatgpt.ps1')) -eq (Get-TradeSha256 $source)) 'Delivered script matches tested source'
        $installed=Join-Path $temp 'Programs'
        $target=Join-Path $installed 'desktop-test/app/scripts/connect-chatgpt.ps1'
        $null=New-Item -ItemType Directory -Force -Path (Split-Path $target -Parent)
        $archive=[IO.Compression.ZipFile]::OpenRead((Join-Path $repo 'downloads/TradeAgent-Desktop-0.2.0-Windows-x64.zip'))
        try {
            $entry=$archive.GetEntry('TradeAgent/app/scripts/connect-chatgpt.ps1')
            $reader=$entry.Open(); $writer=[IO.File]::Create($target)
            try { $reader.CopyTo($writer) } finally { $reader.Dispose(); $writer.Dispose() }
        } finally { $archive.Dispose() }
        $originalHash=Get-TradeSha256 $target
        $privateFile=Join-Path $temp 'data/secrets/gmail-client.json'
        $null=New-Item -ItemType Directory -Force -Path (Split-Path $privateFile -Parent)
        [IO.File]::WriteAllText($privateFile,'private-test-data-do-not-change')
        $engine=Join-Path $PSHOME 'powershell.exe'
        if (-not (Test-Path -LiteralPath $engine)) { $engine=Join-Path $PSHOME 'pwsh' }
        & $engine -NoLogo -NoProfile -ExecutionPolicy Bypass -File (Join-Path $patchRoot 'fix.ps1') -ProgramsRoot $installed
        Assert-True ($LASTEXITCODE -eq 0) 'Patch installer completed'
        Assert-True ((Get-TradeSha256 $target) -eq (Get-TradeSha256 $source)) 'Installed script checksum'
        $backups=@(Get-ChildItem -LiteralPath (Split-Path $target -Parent) -Filter '*.bak')
        Assert-True ($backups.Count -eq 1) 'Original script backed up'
        Assert-True ((Get-TradeSha256 $backups[0].FullName) -eq $originalHash) 'Backup preserves original bytes'
        & $engine -NoLogo -NoProfile -ExecutionPolicy Bypass -File (Join-Path $patchRoot 'fix.ps1') -ProgramsRoot $installed
        Assert-True ($LASTEXITCODE -eq 0) 'Repeated patch is safe'
        Assert-True (@(Get-ChildItem -LiteralPath (Split-Path $target -Parent) -Filter '*.bak').Count -eq 1) 'Repeat does not overwrite backup'
        Assert-True ([IO.File]::ReadAllText($privateFile) -eq 'private-test-data-do-not-change') 'Business and mailbox data untouched'
        [IO.File]::WriteAllText($target,'unknown user-modified script')
        & $engine -NoLogo -NoProfile -ExecutionPolicy Bypass -File (Join-Path $patchRoot 'fix.ps1') -ProgramsRoot $installed
        Assert-True ($LASTEXITCODE -eq 1) 'Unknown script refused'
        Assert-True ([IO.File]::ReadAllText($target) -eq 'unknown user-modified script') 'Unknown script preserved'
    }
    Write-Host "PASS: $script:checks checks; PowerShell $($PSVersionTable.PSVersion)"
} finally { Remove-Item -LiteralPath $temp -Recurse -Force }
