param([ValidateRange(1,65535)][int]$Port = 8765, [switch]$InstallCloudflared, [switch]$ShowApiKey)
. (Join-Path $PSScriptRoot 'common.ps1')
$root = Set-TradeEnvironment -Port $Port

function Get-TradeSha256([string]$Path) {
    $hasher = [Security.Cryptography.SHA256]::Create()
    try {
        $stream = [IO.File]::OpenRead($Path)
        try { return [BitConverter]::ToString($hasher.ComputeHash($stream)).Replace('-', '').ToLowerInvariant() }
        finally { $stream.Dispose() }
    } finally { $hasher.Dispose() }
}

function Get-TradeTunnelUrl([AllowNull()][AllowEmptyString()][string]$Contents) {
    # Get-Content -Raw returns $null while the new redirected log is empty.
    if ([string]::IsNullOrWhiteSpace($Contents)) { return $null }
    $found = [regex]::Matches($Contents, 'https://[a-z0-9-]+\.trycloudflare\.com\b')
    if ($found.Count -gt 0) { return $found[$found.Count - 1].Value }
    return $null
}

function Wait-TradeTunnelUrl {
    param([string]$LogPath, [object]$Process, [ValidateRange(1,300)][int]$Attempts = 90)
    for ($attempt = 0; $attempt -lt $Attempts; $attempt++) {
        $Process.Refresh()
        if ($Process.HasExited) { throw "Connection tool exited (code $($Process.ExitCode)). Inspect: $LogPath" }
        if (Test-Path -LiteralPath $LogPath) {
            $contents = [string](Get-Content -LiteralPath $LogPath -Raw -ErrorAction Stop)
            $url = Get-TradeTunnelUrl -Contents $contents
            if ($url) { return $url }
        }
        if ($attempt % 10 -eq 0) { Write-Host "Waiting for the HTTPS address... $attempt seconds" }
        Start-Sleep -Seconds 1
    }
    throw "No HTTPS address after $Attempts seconds. Inspect: $LogPath. The next run will reuse the same running connection tool."
}

function Get-TradeExistingTunnel {
    param([string]$RecordPath, [string]$RootPath, [string]$Executable, [int]$ExpectedPort)
    if (-not (Test-Path -LiteralPath $RecordPath)) { return $null }
    $record = Get-Content -LiteralPath $RecordPath -Raw | ConvertFrom-Json
    $process = Get-Process -Id ([int]$record.pid) -ErrorAction SilentlyContinue
    if (-not $process) { return $null }
    if ($record.root -ne $RootPath -or $record.role -ne 'tunnel' -or [int]$record.port -ne $ExpectedPort) {
        throw 'The active tunnel record belongs to another folder or port. It was left unchanged.'
    }
    # PID + creation time + full executable path identify the exact process.
    # No CIM dependency: CIM is unavailable on some supported Windows setups.
    $recordedStart = [string]$record.start_time_utc
    if ($record.start_time_utc -is [DateTime] -or $record.start_time_utc -is [DateTimeOffset]) {
        $recordedStart = $record.start_time_utc.ToUniversalTime().ToString('o')
    }
    if ($process.StartTime.ToUniversalTime().ToString('o') -ne $recordedStart -or
        $process.Path -ne $record.executable -or $process.Path -ne $Executable) {
        throw 'Tunnel process identity changed. No process was stopped or reused.'
    }
    return $process
}

function Get-Cloudflared {
    $local = Join-Path $root '.runtime\tools\cloudflared.exe'
    if (Test-Path -LiteralPath $local) { return $local }
    $existing = Get-Command cloudflared.exe -ErrorAction SilentlyContinue
    if ($existing) { return $existing.Source }
    if (-not $InstallCloudflared) {
        throw 'Cloudflared is missing. Run connect-chatgpt.cmd -InstallCloudflared to download a SHA256-verified official release, or install Cloudflare cloudflared yourself.'
    }
    # Keep Windows certificate validation enabled. GitHub provides the expected digest.
    [Net.ServicePointManager]::SecurityProtocol = [Net.ServicePointManager]::SecurityProtocol -bor [Net.SecurityProtocolType]::Tls12
    $release = Invoke-RestMethod -Uri 'https://api.github.com/repos/cloudflare/cloudflared/releases/latest' -Headers @{'User-Agent'='trade-agent-setup'} -TimeoutSec 30
    $architecture = if ($env:PROCESSOR_ARCHITECTURE -eq 'ARM64') { 'arm64' } else { 'amd64' }
    $asset = @($release.assets | Where-Object { $_.name -eq "cloudflared-windows-$architecture.exe" }) | Select-Object -First 1
    if (-not $asset) { throw 'No official Windows executable was found for this architecture.' }
    $digestProperty = $asset.PSObject.Properties['digest']
    $digestMatch = if ($digestProperty) { [regex]::Match([string]$digestProperty.Value, '^sha256:([0-9a-fA-F]{64})$') } else { $null }
    if (-not $digestMatch -or -not $digestMatch.Success) {
        throw 'Official release has no verifiable SHA256 digest. Download/install the official cloudflared release manually; automatic download was refused.'
    }
    $expected = $digestMatch.Groups[1].Value.ToLowerInvariant()
    $download = "$local.download"
    Invoke-WebRequest -UseBasicParsing -Uri $asset.browser_download_url -OutFile $download -TimeoutSec 120
    $actual = Get-TradeSha256 $download
    if ($actual -ne $expected) {
        Remove-Item -LiteralPath $download -Force
        throw 'Cloudflared checksum verification failed; the file was deleted.'
    }
    Move-Item -LiteralPath $download -Destination $local -Force
    Write-Host "Verified official cloudflared release $($release.tag_name)."
    return $local
}

try {
    $health = Get-TradeHealth -Port $Port
    if (-not $health -or -not $health.PSObject.Properties['application'] -or $health.application -ne 'trade_agent') {
        throw 'Run start.cmd before connecting ChatGPT; the port does not serve this application.'
    }
    $bootstrap = Get-TradeBootstrap -Port $Port
    $cloudflared = Get-Cloudflared
    $pidPath = Join-Path $root '.runtime\tunnel.pid.json'
    $existing = Get-TradeExistingTunnel -RecordPath $pidPath -RootPath $root -Executable $cloudflared -ExpectedPort $Port
    $log = Join-Path $root '.runtime\logs\tunnel.stderr.log'
    if (-not $existing) {
        $stdout = Join-Path $root '.runtime\logs\tunnel.stdout.log'
        # Never extract a previous connection's address from a stale log.
        [IO.File]::WriteAllText($log, '')
        [IO.File]::WriteAllText($stdout, '')
        $process = Start-Process -FilePath $cloudflared -ArgumentList @('tunnel', '--url', "http://127.0.0.1:$Port", '--no-autoupdate') -WorkingDirectory $root -PassThru -WindowStyle Hidden -RedirectStandardOutput $stdout -RedirectStandardError $log
        Save-TradeProcess -Process $process -Path $pidPath -Role 'tunnel' -Port $Port
    } else { $process = $existing }
    $publicUrl = Wait-TradeTunnelUrl -LogPath $log -Process $process
    $headers = @{Authorization = "Bearer $($bootstrap.api_key)"}
    $null = Invoke-RestMethod -Uri "http://127.0.0.1:$Port/api/settings" -Method Patch -Headers $headers -ContentType 'application/json' -Body (@{public_url=$publicUrl} | ConvertTo-Json)
    $schema = Join-Path $root '.runtime\openapi-actions.json'
    Invoke-WebRequest -UseBasicParsing -Uri "http://127.0.0.1:$Port/openapi-actions.json" -OutFile $schema -TimeoutSec 10
    Write-Host "Actions schema URL: $publicUrl/openapi-actions.json"
    Write-Host "Local schema copy: $schema"
    Write-Host 'In your custom GPT: Actions -> Import from URL; Authentication -> API Key -> Bearer.'
    Write-Host 'Read docs/GPT-INSTRUCTIONS.zh-CN.md for the instructions to paste into your GPT.'
    Write-Host 'This temporary URL changes after restarting the tunnel. Update the GPT schema when it changes.'
    Write-Host 'The computer, application and tunnel must stay on for ChatGPT to use the tools.'
    Write-Host 'The URL is prepared. Verify access with a status call in GPT Actions; this script does not certify public connectivity.'
    if ($ShowApiKey) {
        Write-Host 'PRIVATE LOCAL SETUP: paste this key into GPT Action authentication only. Do not paste it into chat or share it.'
        Write-Host $bootstrap.api_key
    } else {
        Write-Host 'To display the private key locally for setup, rerun with -ShowApiKey. It is not written to setup logs.'
    }
} catch {
    Write-Host ('ChatGPT connection setup failed: ' + $_.Exception.Message) -ForegroundColor Red
    exit 1
}
