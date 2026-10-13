param([switch]$SkipBrowser)
. (Join-Path $PSScriptRoot 'common.ps1')
$root = Set-TradeEnvironment
Set-Location -LiteralPath $root

try {
    $python = Join-Path $root '.venv\Scripts\python.exe'
    if (-not (Test-Path -LiteralPath $python)) {
        $candidate = Get-Command py.exe -ErrorAction SilentlyContinue
        if ($candidate) {
            Invoke-TradeNative $candidate.Source @('-3', '-c', "import sys; assert sys.version_info >= (3,11), 'Python 3.11+ is required'")
            Invoke-TradeNative $candidate.Source @('-3', '-m', 'venv', (Join-Path $root '.venv'))
        } else {
            $candidate = Get-Command python.exe -ErrorAction SilentlyContinue
            if (-not $candidate) { throw 'Install Python 3.11+ from python.org, then run install.cmd again.' }
            Invoke-TradeNative $candidate.Source @('-c', "import sys; assert sys.version_info >= (3,11), 'Python 3.11+ is required'")
            Invoke-TradeNative $candidate.Source @('-m', 'venv', (Join-Path $root '.venv'))
        }
    }
    Invoke-TradeNative $python @('-c', "import sys; assert sys.version_info >= (3,11), 'Python 3.11+ is required'")
    $dependencyFile = Join-Path $root 'requirements-lock.txt'
    if (-not (Test-Path -LiteralPath $dependencyFile)) {
        $dependencyFile = Join-Path $root 'requirements.txt'
    }
    Invoke-TradeNative $python @('-m', 'pip', 'install', '--disable-pip-version-check', '-r', $dependencyFile)
    if (-not $SkipBrowser) {
        Invoke-TradeNative $python @('-m', 'playwright', 'install', 'chromium')
        Write-Host 'Chromium installed for browser-assisted discovery.'
    } else {
        Write-Host 'Chromium download skipped. Browser discovery can try an installed Chrome or Edge.'
        Write-Host 'If no supported browser can start, install Chromium later by rerunning install.cmd.'
    }
    Invoke-TradeNative $python @('-c', "import fastapi, uvicorn, playwright; print('Application dependencies imported successfully.')")
    Write-Host 'Installation complete. Run start.cmd next.'
    Write-Host 'No email account has been connected and no messages have been sent.'
} catch {
    Write-Error $_
    exit 1
}
