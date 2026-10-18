Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
function Get-Sha256Hex([string]$FilePath) {
    $hasher = [Security.Cryptography.SHA256]::Create()
    try {
        $stream = [IO.File]::OpenRead($FilePath)
        try {
            return [BitConverter]::ToString($hasher.ComputeHash($stream)).Replace('-', '').ToLowerInvariant()
        } finally { $stream.Dispose() }
    } finally { $hasher.Dispose() }
}
try {
    if (-not [Environment]::Is64BitOperatingSystem) { throw '本软件需要64位 Windows 10 或 Windows 11。' }
    $source = [IO.Path]::GetFullPath($PSScriptRoot)
    $manifestPath = Join-Path $source 'bundle-manifest.json'
    if (-not (Test-Path -LiteralPath $manifestPath)) { throw '请先把整个压缩包解压，再双击安装到桌面.cmd。' }
    $manifest = Get-Content -LiteralPath $manifestPath -Raw -Encoding UTF8 | ConvertFrom-Json
    if ($manifest.product -ne 'Trade Agent Desktop' -or $manifest.target -ne 'Windows x64') { throw '软件包清单不匹配。' }
    $programs = Join-Path $env:LOCALAPPDATA 'Programs\TradeAgent'
    $null = New-Item -ItemType Directory -Force -Path $programs
    $stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
    $stage = Join-Path $programs ('.install-' + [Guid]::NewGuid().ToString('N'))
    $destination = Join-Path $programs ('desktop-0.2.0-' + $stamp + '-' + [Guid]::NewGuid().ToString('N').Substring(0, 6))
    $null = New-Item -ItemType Directory -Path $stage
    try {
        $entries = @($manifest.files)
        $index = 0
        foreach ($entry in $entries) {
            $relative = ([string]$entry.path).Replace('/', '\')
            $inputFile = [IO.Path]::GetFullPath((Join-Path $source $relative))
            $outputFile = [IO.Path]::GetFullPath((Join-Path $stage $relative))
            if (-not $inputFile.StartsWith($source + '\', [StringComparison]::OrdinalIgnoreCase) -or -not $outputFile.StartsWith($stage + '\', [StringComparison]::OrdinalIgnoreCase)) { throw '软件包中包含无效路径。' }
            if (-not (Test-Path -LiteralPath $inputFile -PathType Leaf)) { throw "软件包不完整，缺少：$relative" }
            $actual = Get-Sha256Hex $inputFile
            if ($actual -ne [string]$entry.sha256) { throw "文件校验不通过，请重新下载完整软件包：$relative" }
            $null = New-Item -ItemType Directory -Force -Path ([IO.Path]::GetDirectoryName($outputFile))
            Copy-Item -LiteralPath $inputFile -Destination $outputFile
            $index++
            if ($index % 50 -eq 0) {
                Write-Progress -Activity '正在安装外贸工作台' -Status '正在校验并复制软件，业务资料不会覆盖' -PercentComplete ([int](100 * $index / $entries.Count))
            }
        }
        Copy-Item -LiteralPath $manifestPath -Destination (Join-Path $stage 'bundle-manifest.json')
        Copy-Item -LiteralPath (Join-Path $source 'SHA256SUMS.txt') -Destination (Join-Path $stage 'SHA256SUMS.txt')
        [IO.Directory]::Move($stage, $destination)
    } finally {
        if (Test-Path -LiteralPath $stage) { Remove-Item -LiteralPath $stage -Recurse -Force }
    }
    Write-Progress -Activity '正在安装外贸工作台' -Completed
    $shortcutDirs = @([Environment]::GetFolderPath('DesktopDirectory'), [Environment]::GetFolderPath('Programs'))
    foreach ($directory in $shortcutDirs) { $null = New-Item -ItemType Directory -Force -Path $directory }
    $shortcutArgs = @('--install-shortcuts', '--desktop-dir', ('"' + $shortcutDirs[0] + '"'), '--start-menu-dir', ('"' + $shortcutDirs[1] + '"'))
    $shortcutError = Join-Path $destination 'shortcut-install.log'
    $shortcutProcess = Start-Process -FilePath (Join-Path $destination 'TradeAgent.exe') -ArgumentList $shortcutArgs -Wait -PassThru -RedirectStandardError $shortcutError
    if ($shortcutProcess.ExitCode -ne 0) {
        $detail = [IO.File]::ReadAllText($shortcutError)
        throw ("创建桌面快捷方式失败（" + $shortcutProcess.ExitCode + "）：" + $detail)
    }
    Write-Host '安装完成！以后双击桌面的“外贸工作台”即可使用。' -ForegroundColor Green
    Write-Host '业务资料保存于：' (Join-Path $env:LOCALAPPDATA 'TradeAgent\data')
    Write-Host '首次启动时，已有旧版资料请选择“是”，再选择旧工作台文件夹。'
    Start-Process -FilePath (Join-Path $destination 'TradeAgent.exe') -WorkingDirectory $destination
} catch {
    Write-Host ('安装未完成：' + $_.Exception.Message) -ForegroundColor Red
    Write-Host ('错误类型：' + $_.Exception.GetType().FullName + ' / HRESULT ' + $_.Exception.HResult)
    if ($null -ne $_.Exception.InnerException) { Write-Host ('内部错误：' + $_.Exception.InnerException.GetType().FullName + ' / ' + $_.Exception.InnerException.Message) }
    Write-Host ('错误位置：' + $_.InvocationInfo.PositionMessage)
    Write-Host ('调用位置：' + $_.ScriptStackTrace)
    Read-Host '按回车关闭，可保留此提示以便排查'
    exit 1
}
