param([string]$ProgramsRoot = (Join-Path $env:LOCALAPPDATA 'Programs\TradeAgent'))
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
function Get-Sha256([string]$Path) {
    $algorithm = [Security.Cryptography.SHA256]::Create()
    try {
        $stream = [IO.File]::OpenRead($Path)
        try { return [BitConverter]::ToString($algorithm.ComputeHash($stream)).Replace('-', '').ToLowerInvariant() }
        finally { $stream.Dispose() }
    } finally { $algorithm.Dispose() }
}
try {
    $payload = Join-Path $PSScriptRoot 'connect-chatgpt.ps1'
    $expected = '__PATCH_HASH__'
    $original = 'f1ad5d616dccd0f405cefbf8e9cb943a0cbdd42defd22d2111858ed32e7dd503'
    if ((Get-Sha256 $payload) -ne $expected) { throw '修复包校验不通过，请重新下载并完整解压。' }
    $tokens=$null; $parseErrors=$null
    $null=[Management.Automation.Language.Parser]::ParseFile($payload,[ref]$tokens,[ref]$parseErrors)
    if ($parseErrors.Count -gt 0) { throw '连接脚本语法检查未通过，没有修改程序。' }
    if (-not (Test-Path -LiteralPath $ProgramsRoot -PathType Container)) { throw '没有找到已安装的外贸工作台，请先确认桌面版已安装。' }
    $targets=@()
    foreach ($folder in Get-ChildItem -LiteralPath $ProgramsRoot -Directory -Filter 'desktop-*') {
        $file=Join-Path $folder.FullName 'app\scripts\connect-chatgpt.ps1'
        if (Test-Path -LiteralPath $file -PathType Leaf) {
            $hash=Get-Sha256 $file
            if ($hash -ne $original -and $hash -ne $expected) {
                throw "发现另一个版本或自行修改过的脚本，已保留，请将这条提示发给技术支持：$file"
            }
            $targets+= [pscustomobject]@{Path=$file; Hash=$hash}
        }
    }
    if ($targets.Count -eq 0) { throw '已安装目录中没有找到连接脚本。' }
    foreach ($target in $targets) {
        if ($target.Hash -eq $expected) { Write-Host ('已经修复：' + $target.Path); continue }
        $stamp=[Guid]::NewGuid().ToString('N')
        $temporary=$target.Path + '.' + $stamp + '.tmp'
        $backup=$target.Path + '.before-chatgpt-fix-' + $stamp + '.bak'
        try {
            Copy-Item -LiteralPath $payload -Destination $temporary
            if ((Get-Sha256 $temporary) -ne $expected) { throw '复制后的脚本校验失败。' }
            [IO.File]::Replace($temporary,$target.Path,$backup)
            if ((Get-Sha256 $target.Path) -ne $expected) { throw '安装后校验失败，请保留窗口和备份。' }
            Write-Host ('已修复：' + $target.Path) -ForegroundColor Green
            Write-Host ('原脚本备份：' + $backup)
        } finally {
            if (Test-Path -LiteralPath $temporary) { Remove-Item -LiteralPath $temporary -Force }
        }
    }
    Write-Host ''
    Write-Host '修复完成。请回到原程序文件夹，再次双击“连接ChatGPT”。' -ForegroundColor Green
    Write-Host '邮箱授权、客户资料和业务设置均保持不变。无需重新安装工作台。'
    exit 0
} catch {
    Write-Host ('修复未完成：' + $_.Exception.Message) -ForegroundColor Red
    exit 1
}
