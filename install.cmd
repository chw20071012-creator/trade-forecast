@echo off
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\install.ps1" %*
set "task_exit_code=%errorlevel%"
if not "%task_exit_code%"=="0" pause
exit /b %task_exit_code%
