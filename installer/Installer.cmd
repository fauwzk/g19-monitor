@echo off
rem Double-clic : installe G19 Monitor pour cet utilisateur (pas besoin des droits administrateur).
chcp 65001 >nul
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0install.ps1" %*
echo.
pause
