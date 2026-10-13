param([ValidateRange(1,65535)][int]$Port = 8765, [switch]$NoBrowser, [switch]$Foreground)
. (Join-Path $PSScriptRoot 'common.ps1')
$root = Set-TradeEnvironment -Port $Port
Set-Location -LiteralPath $root
$python = Get-TradePython
$pidPath = Join-Path $root '.runtime\server.pid.json'

try {
    $existing = Get-TradeOwnedProcess -Path $pidPath -Role 'server'
    if ($existing) {
        $record = Get-Content -LiteralPath $pidPath -Raw | ConvertFrom-Json
        if ([int]$record.port -ne $Port) { throw "This application is already running on port $($record.port). Use the same -Port or stop it first." }
        if (-not (Get-TradeHealth -Port $Port)) { throw 'The recorded server is running but not healthy. Inspect its logs before restarting.' }
        Write-Host 'This application is already running. Use stop.cmd before changing its port.'
        if (-not $NoBrowser) { Start-Process "http://127.0.0.1:$Port/" }
        exit 0
    }
    if (Get-TradeHealth -Port $Port) { throw "Port $Port already serves an application not owned by this launcher." }
    if ($Foreground) {
        Write-Host "Starting http://127.0.0.1:$Port/ in this window. Keep it open; press Ctrl+C to stop."
        if (-not $NoBrowser) { Start-Process "http://127.0.0.1:$Port/" }
        Invoke-TradeNative $python @('-m', 'trade_agent', '--host', '127.0.0.1', '--port', [string]$Port)
        exit 0
    }
    $stdout = Join-Path $root '.runtime\logs\server.stdout.log'
    $stderr = Join-Path $root '.runtime\logs\server.stderr.log'
    $process = Start-Process -FilePath $python -ArgumentList @('-m', 'trade_agent', '--host', '127.0.0.1', '--port', [string]$Port) -WorkingDirectory $root -PassThru -WindowStyle Hidden -RedirectStandardOutput $stdout -RedirectStandardError $stderr
    Save-TradeProcess -Process $process -Path $pidPath -Role 'server' -Port $Port
    $ready = $false
    for ($attempt = 0; $attempt -lt 30; $attempt++) {
        if ($process.HasExited) { throw "Server exited. Inspect $stderr" }
        if (Get-TradeHealth -Port $Port) { $ready = $true; break }
        Start-Sleep -Seconds 1
    }
    if (-not $ready) { throw "Server did not become ready. Inspect $stderr" }
    Write-Host "Ready: http://127.0.0.1:$Port/"
    Write-Host 'Only user-started tasks run. Run stop.cmd before copying the folder.'
    if (-not $NoBrowser) { Start-Process "http://127.0.0.1:$Port/" }
} catch {
    Write-Error $_
    exit 1
}
