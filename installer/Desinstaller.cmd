@echo off
rem Double-clic : retire G19 Monitor (les réglages peuvent être gardés).
chcp 65001 >nul
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0uninstall.ps1" %*
echo.
pause
