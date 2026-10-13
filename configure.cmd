@echo off
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\configure.ps1" %*
set "task_exit_code=%errorlevel%"
echo Review the setup status in this window before closing.
pause
exit /b %task_exit_code%
