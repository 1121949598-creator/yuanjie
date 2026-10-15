@echo off
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\start_teammate.ps1"
if errorlevel 1 echo Operation failed. See the error above.
pause
