Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

function Get-TradeRoot {
    return [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
}

function Set-TradeEnvironment {
    param([int]$Port = 8765)
    $root = Get-TradeRoot
    $runtime = Join-Path $root '.runtime'
    foreach ($relative in @('data', 'data\secrets', 'logs', 'tools', 'browsers', 'tmp', 'cache')) {
        $null = New-Item -ItemType Directory -Force -Path (Join-Path $runtime $relative)
    }
    $env:TRADE_DATA_DIR = Join-Path $runtime 'data'
    $env:TRADE_API_KEY_FILE = Join-Path $runtime 'data\secrets\api-key.txt'
    $env:TRADE_HOST = '127.0.0.1'
    $env:TRADE_PORT = [string]$Port
    $env:PLAYWRIGHT_BROWSERS_PATH = Join-Path $runtime 'browsers'
    $env:PIP_CACHE_DIR = Join-Path $runtime 'cache\pip'
    $env:TEMP = Join-Path $runtime 'tmp'
    $env:TMP = $env:TEMP
    return $root
}

function Get-TradePython {
    $python = Join-Path (Get-TradeRoot) '.venv\Scripts\python.exe'
    if (-not (Test-Path -LiteralPath $python)) {
        throw 'Run install.cmd first: the application virtual environment is missing.'
    }
    return $python
}

function Invoke-TradeNative {
    param([string]$Executable, [string[]]$Arguments)
    & $Executable @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "Command failed with exit code $LASTEXITCODE`: $Executable"
    }
}

function Get-TradeHealth {
    param([int]$Port = 8765)
    try {
        return Invoke-RestMethod -Uri "http://127.0.0.1:$Port/health" -Method Get -TimeoutSec 3
    } catch { return $null }
}

function Get-TradeBootstrap {
    param([int]$Port = 8765)
    return Invoke-RestMethod -Uri "http://127.0.0.1:$Port/local/bootstrap" -Method Get -TimeoutSec 5
}

function Save-TradeProcess {
    param([Diagnostics.Process]$Process, [string]$Path, [string]$Role, [int]$Port)
    $record = @{
        pid = $Process.Id
        start_time_utc = $Process.StartTime.ToUniversalTime().ToString('o')
        executable = $Process.Path
        root = Get-TradeRoot
        role = $Role
        port = $Port
    }
    $record | ConvertTo-Json | Set-Content -LiteralPath $Path -Encoding UTF8
}

function Get-TradeOwnedProcess {
    param([string]$Path, [string]$Role)
    if (-not (Test-Path -LiteralPath $Path)) { return $null }
    $record = Get-Content -LiteralPath $Path -Raw | ConvertFrom-Json
    $process = Get-Process -Id ([int]$record.pid) -ErrorAction SilentlyContinue
    if (-not $process) { return $null }
    if ($record.root -ne (Get-TradeRoot) -or $record.role -ne $Role) {
        throw 'Process record does not belong to this application folder.'
    }
    $started = $process.StartTime.ToUniversalTime().ToString('o')
    if ($started -ne $record.start_time_utc -or $process.Path -ne $record.executable) {
        throw 'Process ID was reused or its executable changed. Refusing to stop it.'
    }
    $command = (Get-CimInstance Win32_Process -Filter "ProcessId = $($process.Id)").CommandLine
    if ($Role -eq 'server' -and $command -notmatch '(^|\s)-m\s+trade_agent(\s|$)') {
        throw 'Recorded process is not the trade_agent server.'
    }
    if ($Role -eq 'tunnel' -and $command -notmatch 'tunnel\s+--url\s+http://127\.0\.0\.1:') {
        throw 'Recorded process is not this local HTTPS tunnel.'
    }
    return $process
}
