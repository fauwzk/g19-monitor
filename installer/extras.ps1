# Logiciels complémentaires de G19 Monitor : Logitech Gaming Software (pilote de l'écran du
# G19) et LibreHardwareMonitor (capteurs, ventilateurs). Chargé par install.ps1 ; les fonctions
# ne font rien d'irréversible sans qu'on les appelle.

$LcorePath = Join-Path $env:ProgramFiles "Logitech Gaming Software\LCore.exe"
$LhmTask = "LibreHardwareMonitor"      # même nom que la tâche que LHM crée lui-même

function Test-Lgs { Test-Path $LcorePath }

function Find-Lhm {
    # tâche planifiée existante, processus en cours, installation winget, dossiers usuels
    $t = Get-ScheduledTask -TaskName $LhmTask -ErrorAction SilentlyContinue
    if ($t -and $t.Actions[0].Execute -and (Test-Path $t.Actions[0].Execute)) { return $t.Actions[0].Execute }
    $p = Get-Process LibreHardwareMonitor -ErrorAction SilentlyContinue | Where-Object Path | Select-Object -First 1
    if ($p) { return $p.Path }
    $roots = @("$env:LOCALAPPDATA\Microsoft\WinGet\Packages", "$env:ProgramFiles", "${env:ProgramFiles(x86)}",
               "$env:LOCALAPPDATA\Programs", "$env:USERPROFILE\Tools")
    foreach ($r in $roots) {
        if (-not (Test-Path $r)) { continue }
        $f = Get-ChildItem $r -Filter LibreHardwareMonitor.exe -Recurse -Depth 3 -ErrorAction SilentlyContinue |
            Select-Object -First 1
        if ($f) { return $f.FullName }
    }
    return $null
}

function Set-LhmConfig($configPath) {
    # Serveur web activé (l'appli lit http://localhost:8085/data.json), démarrage réduit dans la
    # zone de notification. Les options déjà réglées par l'utilisateur sont gardées, sauf le
    # serveur web, forcé ; sur une config neuve, écoute limitée à ce PC.
    $defaults = [ordered]@{ runWebServerMenuItem = "true"; startMinMenuItem = "true";
        minTrayMenuItem = "true"; minCloseMenuItem = "true"; listenerPort = "8085";
        listenerIp = "localhost"; authenticationEnabled = "false" }
    if (Test-Path $configPath) {
        [xml]$xml = Get-Content $configPath -Raw -Encoding UTF8
    } else {
        [xml]$xml = '<?xml version="1.0" encoding="utf-8"?><configuration><appSettings /></configuration>'
    }
    $settings = $xml.configuration.SelectSingleNode("appSettings")
    if (-not $settings) { $settings = $xml.configuration.AppendChild($xml.CreateElement("appSettings")) }
    foreach ($key in $defaults.Keys) {
        $node = $settings.SelectSingleNode("add[@key='$key']")
        if (-not $node) {
            $node = $settings.AppendChild($xml.CreateElement("add"))
            $node.SetAttribute("key", $key)
            $node.SetAttribute("value", $defaults[$key])
        } elseif ($key -eq "runWebServerMenuItem") {
            $node.SetAttribute("value", "true")
        }
    }
    $xml.Save($configPath)
}

function Get-LhmTaskScript($exe) {
    # tâche « à l'ouverture de session », droits les plus élevés (LHM en a besoin pour lire les
    # capteurs et piloter les ventilateurs), aussi sur batterie, sans limite de durée
    $user = "$env:USERDOMAIN\$env:USERNAME"
    return @"
`$a = New-ScheduledTaskAction -Execute '$exe' -WorkingDirectory '$(Split-Path $exe)'
`$t = New-ScheduledTaskTrigger -AtLogOn -User '$user'
`$p = New-ScheduledTaskPrincipal -UserId '$user' -LogonType Interactive -RunLevel Highest
`$s = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -ExecutionTimeLimit 0 -MultipleInstances IgnoreNew
Register-ScheduledTask -TaskName '$LhmTask' -Action `$a -Trigger `$t -Principal `$p -Settings `$s -Force | Out-Null
Start-ScheduledTask -TaskName '$LhmTask'
"@
}

function Register-LhmTask($exe) {
    # une seule demande d'élévation (UAC) pour créer la tâche et lancer LHM avec ses droits
    $script = Get-LhmTaskScript $exe
    $encoded = [Convert]::ToBase64String([Text.Encoding]::Unicode.GetBytes($script))
    $proc = Start-Process powershell -Verb RunAs -Wait -PassThru -WindowStyle Hidden `
        -ArgumentList "-NoProfile -ExecutionPolicy Bypass -EncodedCommand $encoded"
    return ($proc -and $proc.ExitCode -eq 0)
}

function Refresh-Path {
    $env:Path = [Environment]::GetEnvironmentVariable("Path", "User") + ";" +
        [Environment]::GetEnvironmentVariable("Path", "Machine")
}
