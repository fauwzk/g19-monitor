@echo off
rem Mise a jour du moniteur G19 : code (si depot git), dependances, puis relance.
cd /d "%~dp0"

if exist ".git" (
    echo == Recuperation du code
    git pull --ff-only || goto :error
)

echo == Dependances
python -m pip install --quiet --upgrade -r requirements.txt || goto :error

echo == Relance
python g19_monitor.py --restart || goto :error
echo.
echo Mise a jour terminee.
timeout /t 3 >nul
exit /b 0

:error
echo.
echo Echec de la mise a jour, voir les messages ci-dessus.
pause
exit /b 1
