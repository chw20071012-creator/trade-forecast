param([ValidateRange(1,65535)][int]$Port = 8765, [switch]$Force)
. (Join-Path $PSScriptRoot 'common.ps1')
$root = Set-TradeEnvironment -Port $Port

try {
    $serverPath = Join-Path $root '.runtime\server.pid.json'
    $tunnelPath = Join-Path $root '.runtime\tunnel.pid.json'
    $server = Get-TradeOwnedProcess -Path $serverPath -Role 'server'
    if ($server -and -not $Force) {
        $record = Get-Content -LiteralPath $serverPath -Raw | ConvertFrom-Json
        if ([int]$record.port -ne $Port) { throw "The server uses port $($record.port). Run stop.cmd -Port $($record.port)." }
        $bootstrap = Get-TradeBootstrap -Port $Port
        $headers = @{Authorization = "Bearer $($bootstrap.api_key)"}
        $tasks = Invoke-RestMethod -Uri "http://127.0.0.1:$Port/api/entities/tasks" -Headers $headers -TimeoutSec 5
        $running = @($tasks | Where-Object { $_.PSObject.Properties['state'] -and $_.state -in @('queued', 'running') })
        if ($running.Count -gt 0) {
            throw 'Tasks are still running. Pause email batches and wait for current work before stopping; use -Force only if you accept interruption.'
        }
        $null = Invoke-RestMethod -Uri "http://127.0.0.1:$Port/api/backup" -Method Post -Headers $headers -ContentType 'application/json' -Body '{}' -TimeoutSec 20
        Write-Host 'Backup saved before stopping.'
    }
    $tunnel = Get-TradeOwnedProcess -Path $tunnelPath -Role 'tunnel'
    if ($tunnel) { Stop-Process -Id $tunnel.Id; Remove-Item -LiteralPath $tunnelPath -Force }
    if ($server) { Stop-Process -Id $server.Id; Remove-Item -LiteralPath $serverPath -Force }
    Write-Host 'Stopped the processes recorded for this application folder.'
} catch {
    Write-Error $_
    exit 1
}
