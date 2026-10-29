"""Alertes système (bandeau) : Windows attend un redémarrage (mise à jour), ou un disque passe
sous l'espace libre minimal réglé. Vérifié toutes les 5 min, rappelé toutes les 6 h."""
import threading
import time
import winreg

import psutil

EVERY = 300
REMIND = 6 * 3600

# clés présentes tant qu'un redémarrage est attendu
REBOOT_KEYS = [
    r"SOFTWARE\Microsoft\Windows\CurrentVersion\WindowsUpdate\Auto Update\RebootRequired",
    r"SOFTWARE\Microsoft\Windows\CurrentVersion\Component Based Servicing\RebootPending",
]


def reboot_pending():
    for path in REBOOT_KEYS:
        try:
            winreg.CloseKey(winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, path))
            return True
        except OSError:
            pass
    return False


def low_disks(min_free_gb):
    """[(lecteur, Go libres, % libre)] des disques fixes sous le seuil."""
    out = []
    for part in psutil.disk_partitions(all=False):
        if "fixed" not in part.opts and "rw" not in part.opts:
            continue
        try:
            u = psutil.disk_usage(part.mountpoint)
        except OSError:
            continue
        free_gb = u.free / 2**30
        if u.total > 8 * 2**30 and free_gb < min_free_gb:
            out.append((part.mountpoint.rstrip("\\"), free_gb, 100 - u.percent))
    return out


class SystemWatch:
    def __init__(self, settings_fn):
        self.settings_fn = settings_fn
        self.event = None        # (titre, texte, horodatage)
        self.reboot = False
        self.disks = []
        self._told = {}          # clé d'alerte → dernier rappel
        self._wake = threading.Event()
        threading.Thread(target=self._run, daemon=True).start()

    def check_now(self):
        self._wake.set()

    def _run(self):
        time.sleep(20)           # laisse l'appli démarrer avant la première vérification
        while True:
            try:
                self._check()
            except Exception:
                pass
            self._wake.wait(EVERY)
            self._wake.clear()

    def _tell(self, key, title, body):
        now = time.time()
        if now - self._told.get(key, 0) >= REMIND:
            self._told[key] = now
            self.event = (title, body, now)

    def _check(self):
        cfg = self.settings_fn() or {}
        if not cfg.get("sys_alerts", True):
            return
        self.reboot = reboot_pending()
        if self.reboot:
            self._tell("reboot", "Redémarrage requis", "Windows a installé des mises à jour")
        else:
            self._told.pop("reboot", None)
        self.disks = low_disks(cfg.get("disk_free_gb", 15))
        for drive, free_gb, free_pct in self.disks:
            self._tell(f"disk:{drive}", f"Disque {drive} presque plein",
                       f"{free_gb:.1f} Go libres ({free_pct:.0f} %)".replace(".", ","))
        for key in [k for k in self._told if k.startswith("disk:")]:
            if key[5:] not in {d for d, _, _ in self.disks}:
                self._told.pop(key)
