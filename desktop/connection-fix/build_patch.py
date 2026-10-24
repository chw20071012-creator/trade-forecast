from pathlib import Path
import hashlib
import zipfile
import sys

root = Path(__file__).resolve().parents[2]
script = (root / 'scripts/connect-chatgpt.ps1').read_bytes()
digest = hashlib.sha256(script).hexdigest()
installer = (Path(__file__).parent / 'fix.ps1').read_text(encoding='utf-8-sig')
installer = installer.replace('__PATCH_HASH__', digest).replace('\r\n', '\n').replace('\n', '\r\n')
files = {
    'connect-chatgpt.ps1': script,
    'fix.ps1': installer.encode('utf-8-sig'),
    '修复ChatGPT连接.cmd': b'@echo off\r\npowershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0fix.ps1"\r\nset "patch_exit=%ERRORLEVEL%"\r\npause\r\nexit /b %patch_exit%\r\n',
    '使用说明.txt': ('外贸工作台 ChatGPT 连接修复包\n\n'
        '1. 右键ZIP选择全部解压，不要在压缩包里运行。\n'
        '2. 双击“修复ChatGPT连接.cmd”。脚本会自动定位已安装的桌面版、校验版本并备份原连接脚本。\n'
        '3. 看到“修复完成”后，回原程序文件夹双击“连接ChatGPT”。保持外贸工作台运行。\n'
        '4. 等待出现 Actions schema URL。窗口显示的API Key只填入自己的GPT Actions认证框，不发到聊天。\n\n'
        '本修复只更换连接脚本，保留邮箱授权和业务资料。无需重新安装或重新授权邮箱。\n'
        '修复空日志Matches(null)异常，等待期间显示进度；识别连接进程提前退出；'
        '重试通过PID、启动时间和完整路径识别原进程，无需CIM；保留下载SHA256校验。\n'
        '只有生成公网地址后才准备Actions配置。实际公网访问仍需在GPT Actions测试状态接口。\n'
        '源码和校验结果见发布分支chatgpt-connect-fix。\n').encode('utf-8-sig'),
}
out=root/'downloads/TradeAgent-ChatGPT-Connection-Fix.zip'
out.parent.mkdir(exist_ok=True)
if '--verify' in sys.argv:
    checksum=hashlib.sha256(out.read_bytes()).hexdigest()
    assert checksum == Path(str(out)+'.sha256').read_text().split()[0], 'Delivered ZIP checksum mismatch'
    with zipfile.ZipFile(out) as z:
        assert z.testzip() is None, 'ZIP CRC failure'
        assert set(z.namelist()) == {'TradeAgent-ChatGPT-Fix/'+name for name in files}, 'Unexpected package files'
        for name,data in files.items():
            assert z.read('TradeAgent-ChatGPT-Fix/'+name) == data, f'Delivered payload differs from source: {name}'
    print('PASS: delivered ZIP checksum, CRC and every payload match the source')
    sys.exit(0)
with zipfile.ZipFile(out,'w',zipfile.ZIP_DEFLATED) as z:
    for name,data in files.items():
        info=zipfile.ZipInfo('TradeAgent-ChatGPT-Fix/'+name,(2026,10,24,0,0,0))
        info.create_system=3
        info.compress_type=zipfile.ZIP_DEFLATED
        z.writestr(info,data)
with zipfile.ZipFile(out) as z:
    assert z.testzip() is None
    assert z.read('TradeAgent-ChatGPT-Fix/connect-chatgpt.ps1') == script
checksum=hashlib.sha256(out.read_bytes()).hexdigest()
Path(str(out)+'.sha256').write_text(checksum+'  '+out.name+'\n',encoding='ascii')
print(f'{out}\n{out.stat().st_size} bytes\nSHA256 {checksum}')
