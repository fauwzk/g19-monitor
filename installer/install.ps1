# Installation de G19 Monitor sur ce PC (sans droits administrateur).
# Lancé par Installer.cmd ; options pour un essai : -Dest dossier -NoLaunch -NoShortcuts -NoPip
# -NoStop (ne pas arrêter l'appli en cours) -Startup yes|no -Hooks yes|no
param(
    [string]$Dest = (Join-Path $env:LOCALAPPDATA "Programs\G19Monitor"),
    # dépôt GitHub (écrit par build_package.py) : le dossier installé en est un clone, ce qui
    # permet les mises à jour automatiques ; vide = simple copie des fichiers du paquet
    [string]$Repo = "__REPO__",
    [string]$Branch = "__BRANCH__",
    # (les marqueurs __…__ ci-dessus sont remplacés par build_package.py)
    [ValidateSet("ask", "yes", "no")][string]$Startup = "ask",
    [ValidateSet("ask", "yes", "no")][string]$Hooks = "ask",
    [switch]$NoLaunch,
    [switch]$NoShortcuts,
    [switch]$NoPip,
    [switch]$NoStop,
    [ValidateSet("ask", "yes", "no")][string]$Lgs = "ask",
    [ValidateSet("ask", "yes", "no")][string]$Lhm = "ask"
)
# pas "Stop" : sous Windows PowerShell 5, la moindre ligne que git ou python écrit sur stderr
# (une simple astuce de « git init »…) deviendrait une erreur fatale ; les codes de retour
# sont vérifiés à chaque étape
$ErrorActionPreference = "Continue"
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
$src = Join-Path $here "app"
. (Join-Path $here "extras.ps1")     # LGS et LibreHardwareMonitor

function Say($text, $color = "Gray") { Write-Host $text -ForegroundColor $color }
function Step($text) { Write-Host ""; Write-Host "== $text" -ForegroundColor Cyan }
function Ask($question, $answer) {
    if ($answer -ne "ask") { return $answer -eq "yes" }
    $r = Read-Host "$question [O/n]"
    return ($r -eq "" -or $r -match "^[oOyY]")
}

function Find-Python {
    $cands = @()
    if (Get-Command py -ErrorAction SilentlyContinue) {
        $p = & py -3 -c "import sys; print(sys.executable)" 2>$null
        if ($p) { $cands += $p }
    }
    foreach ($n in "python", "python3") {
        $c = Get-Command $n -ErrorAction SilentlyContinue
        # le « python » de WindowsApps n'est qu'un raccourci vers le Store
        if ($c -and $c.Source -notlike "*WindowsApps*") { $cands += $c.Source }
    }
    $cands += Get-ChildItem "$env:LOCALAPPDATA\Programs\Python\Python3*\python.exe",
        "$env:ProgramFiles\Python3*\python.exe" -ErrorAction SilentlyContinue |
        ForEach-Object FullName
    $found = @()
    foreach ($p in ($cands | Select-Object -Unique)) {
        $v = & $p -c "import sys; print('%d.%d' % sys.version_info[:2])" 2>$null
        if ($v -and [version]$v -ge [version]"3.10") {
            $found += [pscustomobject]@{ Path = $p; Version = [version]$v }
        }
    }
    if (-not $found) { return $null }
    $ok = $found | Where-Object { $_.Version -le [version]"3.13" } | Sort-Object Version -Descending
    if ($ok) { return @($ok)[0].Path }
    return @($found | Sort-Object Version -Descending)[0].Path
}

Say "Installation de G19 Monitor" "White"
Say "Dossier : $Dest"

Step "Python"
$py = Find-Python
if (-not $py) {
    Say "Python 3.10 ou plus récent est introuvable." "Yellow"
    if ((Get-Command winget -ErrorAction SilentlyContinue) -and
        (Ask "L'installer maintenant avec winget (Python 3.13, pour cet utilisateur) ?" "ask")) {
        winget install -e --id Python.Python.3.13 --scope user --silent `
            --accept-package-agreements --accept-source-agreements
        $env:Path = [Environment]::GetEnvironmentVariable("Path", "User") + ";" +
            [Environment]::GetEnvironmentVariable("Path", "Machine")
        $py = Find-Python
    }
    if (-not $py) {
        Say "Installe Python depuis https://www.python.org/downloads/ puis relance Installer.cmd." "Red"
        exit 1
    }
}
$pyw = Join-Path (Split-Path $py) "pythonw.exe"
if (-not (Test-Path $pyw)) { $pyw = $py }
Say "Python : $py"

Step "Arrêt d'une version déjà installée"
if ($NoStop) { Say "ignoré (-NoStop)" }
elseif (Test-Path (Join-Path $Dest "g19_monitor.py")) {
    & $py (Join-Path $Dest "g19_monitor.py") --stop 2>$null | Out-Null
    Say "ok"
} else { Say "aucune" }

function Find-Git {
    $g = Get-Command git -ErrorAction SilentlyContinue
    if ($g) { return $g.Source }
    foreach ($p in "$env:ProgramFiles\Git\cmd\git.exe", "$env:LOCALAPPDATA\Programs\Git\cmd\git.exe") {
        if (Test-Path $p) { return $p }
    }
    return $null
}

function Install-FromGit($git) {
    # clone (ou mise à jour d'un clone existant) ; un dossier déjà rempli par une simple copie
    # est repris : les fichiers suivis sont remplacés par ceux du dépôt
    New-Item -ItemType Directory -Force $Dest | Out-Null
    if (-not (Test-Path (Join-Path $Dest ".git"))) {
        & $git -C $Dest init -q 2>&1 | Out-Null
        & $git -C $Dest remote add origin $Repo 2>&1 | Out-Null
    }
    & $git -C $Dest fetch -q origin $Branch 2>&1 | Out-Null
    if ($LASTEXITCODE -ne 0) { return $false }
    & $git -C $Dest checkout -q -f -B $Branch "origin/$Branch" 2>&1 | Out-Null
    if ($LASTEXITCODE -ne 0) { return $false }
    & $git -C $Dest branch -q --set-upstream-to "origin/$Branch" $Branch 2>&1 | Out-Null
    return $true
}

Step "Code de l'appli"
$fromGit = $false
if ($Repo -and $Repo -notlike "__*__") {      # « __REPO__ » : paquet construit hors dépôt git
    $git = Find-Git
    if (-not $git -and (Get-Command winget -ErrorAction SilentlyContinue) -and
        (Ask "Installer Git (nécessaire pour les mises à jour automatiques ; Windows demandera les droits administrateur) ?" "ask")) {
        winget install -e --id Git.Git --silent --accept-package-agreements --accept-source-agreements
        $env:Path = [Environment]::GetEnvironmentVariable("Path", "User") + ";" +
            [Environment]::GetEnvironmentVariable("Path", "Machine")
        $git = Find-Git
    }
    if ($git) {
        Say "depuis $Repo"
        $fromGit = Install-FromGit $git
        if (-not $fromGit) { Say "GitHub injoignable : copie des fichiers du paquet à la place." "Yellow" }
    } else {
        Say "Git absent : copie des fichiers du paquet, sans mises à jour automatiques." "Yellow"
    }
}
if (-not $fromGit) {
    New-Item -ItemType Directory -Force $Dest | Out-Null
    robocopy $src $Dest /E /XD __pycache__ /NFL /NDL /NJH /NJS /NP | Out-Null
    if ($LASTEXITCODE -ge 8) { Say "Échec de la copie (robocopy $LASTEXITCODE)." "Red"; exit 1 }
}
Say ("ok" + $(if ($fromGit) { ", mises à jour automatiques depuis GitHub" } else { "" }))
Say "Les réglages, dans %LOCALAPPDATA%\G19Monitor, ne sont pas touchés."

if (-not $NoPip) {
    Step "Bibliothèques Python"
    & $py -m pip install --user --upgrade --disable-pip-version-check -q `
        -r (Join-Path $Dest "requirements.txt")
    if ($LASTEXITCODE -ne 0) { Say "Échec de pip, voir les messages ci-dessus." "Red"; exit 1 }
    Say "ok"
}

Step "Logitech Gaming Software"
if (Test-Lgs) {
    Say "déjà installé"
} elseif (-not (Get-Command winget -ErrorAction SilentlyContinue)) {
    Say "à installer depuis le site de Logitech (Logitech Gaming Software 9.04)." "Yellow"
} elseif (Ask "L'installer (pilote de l'écran du G19 ; Windows demandera les droits administrateur) ?" $Lgs) {
    winget install -e --id Logitech.LGS --silent --accept-package-agreements --accept-source-agreements
    if (Test-Lgs) { Say "ok" "Green" } else { Say "Échec : à installer depuis le site de Logitech." "Yellow" }
} else { Say "non (l'écran du G19 ne fonctionnera pas sans)" }

Step "LibreHardwareMonitor (capteurs et ventilateurs)"
$lhmExe = Find-Lhm
if (-not $lhmExe -and (Get-Command winget -ErrorAction SilentlyContinue) -and
    (Ask "L'installer (températures, ventilateurs ; optionnel) ?" $Lhm)) {
    winget install -e --id LibreHardwareMonitor.LibreHardwareMonitor --silent `
        --accept-package-agreements --accept-source-agreements
    Refresh-Path
    $lhmExe = Find-Lhm
    if (-not $lhmExe) { Say "Échec de l'installation de LibreHardwareMonitor." "Yellow" }
}
if ($lhmExe) {
    Say "trouvé : $lhmExe"
    $web = $false
    try { $web = (Invoke-WebRequest "http://localhost:8085/data.json" -UseBasicParsing -TimeoutSec 3).StatusCode -eq 200 } catch { }
    if ($web) {
        Say "serveur web déjà actif : réglages laissés tels quels"
    } elseif (Get-Process LibreHardwareMonitor -ErrorAction SilentlyContinue) {
        Say "LHM tourne sans serveur web : dans LHM, Options → Remote Web Server → Run." "Yellow"
    } else {
        Set-LhmConfig (Join-Path (Split-Path $lhmExe) "LibreHardwareMonitor.config")
        Say "réglé : serveur web (port 8085, ce PC seulement), démarrage réduit dans la zone de notification"
    }
    if (Get-ScheduledTask -TaskName $LhmTask -ErrorAction SilentlyContinue) {
        Say "lancement au démarrage : déjà en place"
    } elseif (Ask "Le lancer à chaque ouverture de session, avec les droits administrateur dont il a besoin (une demande Windows maintenant) ?" $Lhm) {
        try {
            if (Register-LhmTask $lhmExe) { Say "ok : tâche planifiée créée et LHM lancé" "Green" }
            else { Say "Non fait : dans LHM, Options → Run On Windows Startup." "Yellow" }
        } catch { Say "Refusé : dans LHM, Options → Run On Windows Startup." "Yellow" }
    } else { Say "non" }
} else { Say "non installé (pages GPU / ventilateurs plus limitées)" }

if (-not $NoShortcuts) {
    Step "Raccourcis"
    $sh = New-Object -ComObject WScript.Shell
    $menu = Join-Path ([Environment]::GetFolderPath("Programs")) "G19 Monitor"
    New-Item -ItemType Directory -Force $menu | Out-Null
    $links = @(
        @{ Path = (Join-Path ([Environment]::GetFolderPath("Desktop")) "G19 Monitor.lnk");
           Script = "start_g19.pyw"; Desc = "Lance G19 Monitor" },
        @{ Path = (Join-Path $menu "G19 Monitor.lnk"); Script = "start_g19.pyw";
           Desc = "Lance G19 Monitor" },
        @{ Path = (Join-Path $menu "Réglages G19 Monitor.lnk"); Script = "config_g19.pyw";
           Desc = "Réglages de G19 Monitor" })
    foreach ($l in $links) {
        $s = $sh.CreateShortcut($l.Path)
        $s.TargetPath = $pyw
        $s.Arguments = '"' + (Join-Path $Dest $l.Script) + '"'
        $s.WorkingDirectory = $Dest
        $s.IconLocation = (Join-Path $Dest "g19.ico") + ",0"
        $s.Description = $l.Desc
        $s.Save()
    }
    Say "bureau et menu Démarrer"
}

Step "Démarrage avec Windows"
if (Ask "Lancer G19 Monitor au démarrage de Windows ?" $Startup) {
    & $py (Join-Path $Dest "install_startup.py")
} else { Say "non" }

Step "Voyant Claude Code"
Say "Ajoute des hooks dans ~\.claude\settings.json pour afficher l'état de Claude Code sur le G19."
if (Ask "Les installer ?" $Hooks) {
    & $py (Join-Path $Dest "install_hooks.py")
} else { Say "non (possible plus tard dans les réglages)" }

Step "Terminé"
Say "En option, à installer à part : MSI Afterburner + RivaTuner (capteurs GPU, FPS en jeu)." "Yellow"
Say "Pour reprendre tes réglages : sur l'autre PC, Réglages → Système → Exporter, puis ici Importer."
if (-not $NoLaunch) {
    Start-Process $pyw -ArgumentList ('"' + (Join-Path $Dest "start_g19.pyw") + '"') -WorkingDirectory $Dest
    Say "G19 Monitor est lancé (icône dans la zone de notification)." "Green"
}
