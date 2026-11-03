"""Le gardien sous Linux : un service utilisateur systemd. Il démarre l'appli avec la session
graphique et la relance si elle plante (pas quand on la quitte exprès : sortie 0). Les
relances après une modification du code se font en place (instance.popen → execve), même
processus pour systemd."""
import subprocess
import sys
from pathlib import Path

from .. import instance

NAME = "g19-monitor.service"
UNIT = Path.home() / ".config" / "systemd" / "user" / NAME


def unit_text():
    main = instance.APP_DIR / "g19_monitor.py"
    return f"""[Unit]
Description=G19 Monitor (écran du Logitech G19)
After=graphical-session.target pipewire.service
PartOf=graphical-session.target

[Service]
ExecStart={sys.executable} {main}
WorkingDirectory={instance.APP_DIR}
Restart=on-failure
RestartSec=5
Environment=PYTHONUNBUFFERED=1

[Install]
WantedBy=graphical-session.target
"""


def _ctl(*args):
    return subprocess.run(["systemctl", "--user", *args], capture_output=True, text=True,
                          timeout=15)


def enabled():
    return UNIT.exists() and _ctl("is-enabled", NAME).stdout.strip() == "enabled"


def active():
    return _ctl("is-active", NAME).stdout.strip() == "active"


def set_enabled(on):
    """Active (et écrit) le service, ou le désactive. Ne démarre ni n'arrête l'appli en cours."""
    if on:
        UNIT.parent.mkdir(parents=True, exist_ok=True)
        UNIT.write_text(unit_text(), encoding="utf-8")
        _ctl("daemon-reload")
        return _ctl("enable", NAME).returncode == 0
    _ctl("disable", NAME)
    return True
