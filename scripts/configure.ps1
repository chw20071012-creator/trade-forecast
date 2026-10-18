param(
    [ValidateRange(1,65535)][int]$Port = 8765,
    [string]$ClientJsonPath = '',
    [switch]$SkipMail,
    [switch]$SkipChatGPT
)

. (Join-Path $PSScriptRoot 'common.ps1')
$root = Get-TradeRoot
$dataPath = Join-Path $root '.runtime\data'
# Capture this before the existing environment helper creates directories.
$newDataDirectory = -not (Test-Path -LiteralPath $dataPath)
$root = Set-TradeEnvironment -Port $Port
Set-Location -LiteralPath $root
$baseUrl = "http://127.0.0.1:$Port"
$setupIncomplete = $false

function Invoke-SetupScript {
    param([string]$Name, [string[]]$ScriptArguments = @())
    $shell = (Get-Command powershell.exe -ErrorAction Stop).Source
    $scriptPath = Join-Path $PSScriptRoot $Name
    # Separate processes contain exit statements used by the existing scripts.
    & $shell -NoProfile -ExecutionPolicy Bypass -File $scriptPath @ScriptArguments | Out-Host
    return [int]$LASTEXITCODE
}

function Open-SetupDocument {
    param([string]$Name)
    $document = Join-Path $root ('docs\' + $Name)
    try {
        Start-Process -FilePath 'notepad.exe' -ArgumentList @(('"{0}"' -f $document))
    } catch {
        Write-Host "Open this local guide manually: $document"
    }
}

function Copy-DesktopOAuthClient {
    param([string]$InputPath, [string]$Destination)
    if (Test-Path -LiteralPath $Destination) {
        Write-Host 'An existing Gmail OAuth client was retained. It was not overwritten.'
        return
    }
    $source = Get-Item -LiteralPath $InputPath -ErrorAction Stop
    if ($source.PSProvider.Name -ne 'FileSystem' -or $source.PSIsContainer -or $source.Extension -ne '.json' -or $source.Length -gt 1048576) {
        throw 'Select a Google Desktop OAuth JSON file of at most 1 MB.'
    }
    try {
        $text = Get-Content -LiteralPath $source.FullName -Raw -Encoding UTF8
        $text = $text.TrimStart([char]0xFEFF)
        $client = $text | ConvertFrom-Json
    } catch {
        throw 'The selected file is not readable OAuth JSON. Its contents were not displayed.'
    }
    $installedProperty = $client.PSObject.Properties['installed']
    if (-not $installedProperty -or -not $installedProperty.Value) {
        throw 'The JSON must contain an installed Desktop app client, not a Web app client.'
    }
    $installed = $installedProperty.Value
    $idProperty = $installed.PSObject.Properties['client_id']
    $secretProperty = $installed.PSObject.Properties['client_secret']
    if (-not $idProperty -or -not $secretProperty -or $idProperty.Value -isnot [string] -or $secretProperty.Value -isnot [string] -or [string]$idProperty.Value -notmatch '^[A-Za-z0-9._-]+\.apps\.googleusercontent\.com$' -or [string]::IsNullOrWhiteSpace([string]$secretProperty.Value)) {
        throw 'The Desktop app client ID or secret is missing or invalid. Download the JSON from Google Cloud Console.'
    }
    $stream = $null
    $writer = $null
    $created = $false
    try {
        # CreateNew prevents overwriting even if another process creates the file.
        $stream = [IO.File]::Open($Destination, [IO.FileMode]::CreateNew, [IO.FileAccess]::Write, [IO.FileShare]::None)
        $created = $true
        $writer = [IO.StreamWriter]::new($stream, [Text.UTF8Encoding]::new($false))
        $writer.Write($text)
        $writer.Flush()
    } catch {
        if ($writer) { $writer.Dispose(); $writer = $null }
        if ($stream) { $stream.Dispose(); $stream = $null }
        if ($created) { Remove-Item -LiteralPath $Destination -Force -ErrorAction SilentlyContinue }
        throw 'The local OAuth client could not be copied. Existing credentials were not overwritten.'
    } finally {
        if ($writer) { $writer.Dispose() }
        elseif ($stream) { $stream.Dispose() }
    }
    Write-Host 'Desktop OAuth JSON copied into the local secrets directory; its contents were not displayed.'
}

try {
    Write-Host 'Preparing the local workbench. Windows execution still requires verification on this computer.'
    $python = Join-Path $root '.venv\Scripts\python.exe'
    $dependenciesReady = $false
    if (Test-Path -LiteralPath $python) {
        & $python -c "import sys,fastapi,uvicorn,playwright,openpyxl,docx,httpx,pydantic,multipart,pypdf; assert sys.version_info >= (3,11), 'Python 3.11+ required'" 1>$null 2>$null
        $dependenciesReady = $LASTEXITCODE -eq 0
    }
    if (-not $dependenciesReady) {
        Write-Host 'Installing missing runtime dependencies. Chromium download is skipped; installed Chrome/Edge can be tried.'
        $result = Invoke-SetupScript -Name 'install.ps1' -ScriptArguments @('-SkipBrowser')
        if ($result -ne 0) { throw 'Dependency installation did not complete. Read the installation error and the local configuration guide.' }
    } else {
        Write-Host 'Existing application dependencies are available; installation was not repeated.'
    }

    $result = Invoke-SetupScript -Name 'start.ps1' -ScriptArguments @('-Port', [string]$Port)
    if ($result -ne 0) { throw 'The workbench did not start. Existing processes were not stopped.' }
    $health = Get-TradeHealth -Port $Port
    if (-not $health -or -not $health.PSObject.Properties['application'] -or $health.application -ne 'trade_agent') {
        throw 'The configured local port does not report the expected application.'
    }
    $bootstrap = Get-TradeBootstrap -Port $Port
    $headers = @{Authorization = "Bearer $($bootstrap.api_key)"}
    # Do not print or persist the bootstrap response or authorization headers.
    $status = Invoke-RestMethod -Uri "$baseUrl/api/status" -Headers $headers -TimeoutSec 10
    if ($status.demo_mode -ne $true) {
        Write-Host 'Existing non-demo business settings were detected and retained.'
        Write-Host 'Automatic demo/account setup stopped. No data or reviewed sending rules were changed.'
        Write-Host "Use the existing workbench: $baseUrl/"
        Open-SetupDocument 'CONFIGURE.zh-CN.md'
        exit 0
    }
    if ($newDataDirectory -and [int]$status.counts.customers -eq 0) {
        $null = Invoke-RestMethod -Uri "$baseUrl/api/demo/load" -Method Post -Headers $headers -ContentType 'application/json' -Body '{}' -TimeoutSec 20
        Write-Host 'Authorized synthetic demonstration data loaded into the new empty data directory.'
    } else {
        Write-Host 'Existing data was retained. Demonstration loading was not repeated.'
    }
    Write-Host 'Demo mode retained; no inbox synchronization, customer search or sending task was started.'

    if (-not $SkipMail) {
        try {
            $clientPath = Join-Path $dataPath 'secrets\gmail-client.json'
            if ($ClientJsonPath) { Copy-DesktopOAuthClient -InputPath $ClientJsonPath -Destination $clientPath }
            $mailStatus = Invoke-RestMethod -Uri "$baseUrl/api/mail/status" -Headers $headers -TimeoutSec 10
            if ($mailStatus.connected) {
                Write-Host 'A local Gmail OAuth token already exists. Live mailbox access has not been checked by this helper.'
            } elseif (Test-Path -LiteralPath $clientPath) {
                $oauth = Invoke-RestMethod -Uri "$baseUrl/api/mail/oauth/start" -Method Post -Headers $headers -ContentType 'application/json' -Body '{}' -TimeoutSec 10
                $authorizationUri = [Uri]$oauth.authorization_url
                if ($authorizationUri.Scheme -ne 'https' -or $authorizationUri.Host -ne 'accounts.google.com') {
                    throw 'The authorization endpoint is not the expected official Google page.'
                }
                Start-Process -FilePath $authorizationUri.AbsoluteUri
                Write-Host 'Google authorization opened in your local browser. Complete it yourself; connection is not yet confirmed.'
            } else {
                Write-Host 'Gmail setup is incomplete: a Google Desktop OAuth JSON file is required.'
                Write-Host 'The official Google Console and local guide will open. No password is requested.'
                Start-Process -FilePath 'https://console.cloud.google.com/apis/library/gmail.googleapis.com'
                Start-Process -FilePath 'https://console.cloud.google.com/apis/credentials'
                Open-SetupDocument 'CONFIGURE.zh-CN.md'
            }
        } catch {
            Write-Host 'Gmail setup remains incomplete. Existing credentials and sending rules were retained.'
            Write-Host 'Check the selected Desktop JSON file and the local guide; no file contents or secrets were displayed.'
            $setupIncomplete = $true
        }
    } else {
        Write-Host 'Gmail authorization was skipped as requested.'
    }

    if (-not $SkipChatGPT) {
        Write-Host 'Preparing the official checksum-verified temporary HTTPS tunnel.'
        Write-Host 'The following existing connector displays the private Action key only in this local console.'
        $result = Invoke-SetupScript -Name 'connect-chatgpt.ps1' -ScriptArguments @('-Port', [string]$Port, '-InstallCloudflared', '-ShowApiKey')
        if ($result -ne 0) {
            Write-Host 'Temporary HTTPS setup did not complete. The local workbench remains running; GPT is not connected.'
            $setupIncomplete = $true
        } else {
            Write-Host 'Temporary HTTPS entry prepared. Configure and test the Action in your private GPT; it is not connected automatically.'
        }
        try { Start-Process -FilePath 'https://chatgpt.com/gpts/editor' } catch { Write-Host 'Open https://chatgpt.com/gpts/editor yourself.' }
        Open-SetupDocument 'GPT-INSTRUCTIONS.zh-CN.md'
    } else {
        Write-Host 'ChatGPT tunnel setup was skipped as requested.'
    }

    Write-Host "Local workbench: $baseUrl/"
    Write-Host 'No email was sent, no paid service was purchased, and no GPT account connection was assumed.'
    Write-Host 'Gmail consent and GPT Action authentication must be completed in your own browser.'
    Write-Host 'Keep this console private. Do not paste the Action key, OAuth JSON or tokens into a chat.'
    Open-SetupDocument 'CONFIGURE.zh-CN.md'
    if ($setupIncomplete) { exit 1 }
    exit 0
} catch {
    Write-Host 'Configuration stopped before completion. The helper did not clear business data or send email.'
    Write-Host $_.Exception.Message
    Open-SetupDocument 'CONFIGURE.zh-CN.md'
    exit 1
}
