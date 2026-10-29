"""Mise à jour du pilote graphique AMD (Adrenalin) : version installée (registre) comparée au
catalogue de téléchargement que le logiciel AMD tient à jour lui-même dans
%LOCALAPPDATA%\\AMD_Common (rien n'est téléchargé ici). Bandeau à la sortie d'une nouvelle
version, puis rappel une fois par jour tant qu'elle n'est pas installée."""
import json
import os
import re
import sys
import threading
import time
import winreg
from pathlib import Path

from . import settings

EVERY = 3600             # s entre deux lectures (le catalogue change rarement)
FIRST_DELAY = 60         # pas au démarrage : le PC a d'autres choses à faire
REMIND = 24 * 3600
CATALOG_DIR = Path(os.environ.get("LOCALAPPDATA", "")) / "AMD_Common"
UNINSTALL = r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall"


def version_tuple(text):
    """« 26.10.1 » → (26, 10, 1) ; () si illisible."""
    return tuple(int(x) for x in re.findall(r"\d+", (text or "").split("-")[0])[:4])


def installed_version():
    """Version d'AMD Software (Adrenalin) affichée par Windows, ex. « 26.10.1 »."""
    with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, UNINSTALL) as root:
        for i in range(winreg.QueryInfoKey(root)[0]):
            try:
                with winreg.OpenKey(root, winreg.EnumKey(root, i)) as k:
                    name = winreg.QueryValueEx(k, "DisplayName")[0]
                    if name.strip() == "AMD Software":
                        return winreg.QueryValueEx(k, "DisplayVersion")[0]
            except OSError:
                continue
    return None


def gpu_skus():
    """Identifiants des cartes AMD présentes, au format du catalogue : « 744C-CC »."""
    skus = set()
    try:
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE,
                            r"SYSTEM\CurrentControlSet\Enum\PCI") as pci:
            for i in range(winreg.QueryInfoKey(pci)[0]):
                m = re.match(r"VEN_1002&DEV_([0-9A-F]{4}).*&REV_([0-9A-F]{2})",
                             winreg.EnumKey(pci, i), re.I)
                if m:
                    skus.add(f"{m.group(1)}-{m.group(2)}".upper())
    except OSError:
        pass
    return skus


def latest(skus):
    """Dernière version du catalogue AMD valable pour une de ces cartes et cette version de
    Windows : {"version", "date", "notes"} ou None."""
    win = "Win11" if sys.getwindowsversion().build >= 22000 else "Win10"
    best = None
    for path in CATALOG_DIR.glob(f"DrvDldDetails_Consumer_*{win}*.json"):
        try:
            entries = json.loads(path.read_text("utf-8-sig"))
        except (OSError, ValueError):
            continue
        for e in entries if isinstance(entries, list) else []:
            if skus and not skus & {s.upper() for s in e.get("skus", [])}:
                continue
            v = e.get("externalbuildversion") or ""
            if version_tuple(v) and (not best or version_tuple(v) > version_tuple(best["version"])):
                best = {"version": v, "date": e.get("releasedate", ""),
                        "notes": e.get("releasenotes", "")}
    return best


class AmdDriver:
    def __init__(self):
        self.installed = None
        self.available = None    # {"version", "date", "notes"} si plus récente qu'installée
        self.event = None        # (titre, texte, horodatage) pour le bandeau
        threading.Thread(target=self._run, daemon=True).start()

    def _run(self):
        time.sleep(FIRST_DELAY)
        while True:
            try:
                self.check()
            except Exception:
                pass
            time.sleep(EVERY)

    def check(self, now=None):
        now = now or time.time()
        self.installed = installed_version()
        if not self.installed:
            return                       # pas de pilote AMD (ou pas Adrenalin)
        new = latest(gpu_skus())
        if not new or version_tuple(new["version"]) <= version_tuple(self.installed):
            self.available = None
            return
        self.available = new
        # rappel au plus une fois par jour et par version, même après une relance de l'appli
        seen = settings.load_state().get("driver_notified") or {}
        if seen.get("version") == new["version"] and now - seen.get("at", 0) < REMIND:
            return
        settings.save_state(driver_notified={"version": new["version"], "at": now})
        date = new["date"]
        if re.match(r"\d{2}/\d{2}/\d{4}$", date):          # le catalogue est en mm/jj/aaaa
            date = f"{date[3:5]}/{date[:2]}"
        self.event = (f"Pilote AMD {new['version']} disponible",
                      f"installé {self.installed}" + (f" · sorti le {date}" if date else ""), now)
