# Désinstallation de G19 Monitor (lancée par Desinstaller.cmd).
param([string]$Dest = (Join-Path $env:LOCALAPPDATA "Programs\G19Monitor"))
$ErrorActionPreference = "Continue"

function Say($text, $color = "Gray") { Write-Host $text -ForegroundColor $color }

Say "Désinstallation de G19 Monitor ($Dest)" "White"
$py = $null
if (Get-Command py -ErrorAction SilentlyContinue) { $py = & py -3 -c "import sys; print(sys.executable)" 2>$null }
if (-not $py) { $c = Get-Command python -ErrorAction SilentlyContinue; if ($c) { $py = $c.Source } }

if ($py -and (Test-Path (Join-Path $Dest "g19_monitor.py"))) {
    & $py (Join-Path $Dest "g19_monitor.py") --stop 2>$null | Out-Null
    & $py (Join-Path $Dest "install_startup.py") --uninstall
    & $py (Join-Path $Dest "install_hooks.py") --uninstall
}
Remove-Item (Join-Path ([Environment]::GetFolderPath("Desktop")) "G19 Monitor.lnk") -ErrorAction SilentlyContinue
Remove-Item (Join-Path ([Environment]::GetFolderPath("Programs")) "G19 Monitor") -Recurse -ErrorAction SilentlyContinue
Remove-Item $Dest -Recurse -Force -ErrorAction SilentlyContinue
Say "Appli, raccourcis, démarrage automatique et hooks retirés."

$data = Join-Path $env:LOCALAPPDATA "G19Monitor"
if (Test-Path $data) {
    $r = Read-Host "Supprimer aussi les réglages et historiques ($data) ? [o/N]"
    if ($r -match "^[oOyY]") { Remove-Item $data -Recurse -Force; Say "Réglages supprimés." }
    else { Say "Réglages gardés (repris si tu réinstalles)." }
}
Say "Terminé." "Green"
