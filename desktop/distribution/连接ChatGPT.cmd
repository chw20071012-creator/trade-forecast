@echo off
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0app\scripts\connect-chatgpt.ps1" -InstallCloudflared -ShowApiKey
pause
