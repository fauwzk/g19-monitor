"""Gardien de l'appli : relance g19_monitor.py s'il disparaît sans qu'on l'ait quitté.

Lancé par l'appli elle-même (instance.ensure_guard), il tourne à part, sans console :

    pythonw -m g19.guard

Le chien de garde interne (Watchdog) couvre une boucle figée ; ici, c'est le processus qui
meurt : exception, plantage dans un pilote ou une DLL, processus tué. Quitter l'appli exprès
(icône, utilitaire, --stop) pose l'événement GUARD_STOP : le gardien s'arrête avec elle.
Relances espacées si l'appli replante aussitôt ; relance tout de suite quand le code change
(une correction après un plantage)."""
import ctypes
import os
import time
from pathlib import Path

from . import instance
from .instance import _k32

PERIOD = 5              # s entre deux vérifications
ABSENT_CHECKS = 3       # absente 3 fois de suite (10 à 15 s) : pas juste une relance en cours
BACKOFF = (0, 10, 60, 300)   # attente avant la relance selon les relances des 10 dernières min
WINDOW = 600
HERE = Path(__file__).resolve()
LOG = instance.APP_DIR / "g19.log"


def log(msg):
    try:
        with open(LOG, "a", encoding="utf-8") as f:
            f.write(time.strftime("%Y-%m-%d %H:%M:%S") + f" INFO gardien : {msg}\n")
    except OSError:
        pass


def _own_files():
    files = (HERE, HERE.with_name("instance.py"))
    return {p: p.stat().st_mtime for p in files if p.exists()}


class Guard:
    def __init__(self, running=instance.is_running, spawn=instance.spawn,
                 sources=None, clock=time.time):
        self.running, self.spawn, self.clock = running, spawn, clock
        self.sources = sources or instance.SourceWatcher()
        self.absent = 0
        self.fixed = False          # code modifié depuis la disparition de l'appli
        self.launches = []          # heures des relances (fenêtre de WINDOW s)
        self.next_try = 0.0

    def delay(self, now):
        self.launches = [t for t in self.launches if now - t < WINDOW]
        return BACKOFF[min(len(self.launches), len(BACKOFF) - 1)]

    def check(self, stop_requested):
        """Un passage. Renvoie "stop" (quittée exprès), "launch" (relancée) ou None."""
        now = self.clock()
        if self.running():
            self.absent, self.fixed = 0, False
            self.sources.changed()            # modifs déjà reprises par l'appli (relance)
            return None
        if stop_requested:
            return "stop"
        self.absent += 1
        # code modifié pendant l'absence : on n'attend pas la fin de l'espacement (mais
        # toujours ABSENT_CHECKS passages : l'appli se relance peut-être elle-même)
        self.fixed = bool(self.sources.changed()) or self.fixed
        fixed = self.fixed
        if self.absent < ABSENT_CHECKS:
            return None
        if self.next_try == 0.0:
            wait = self.delay(now)
            self.next_try = now + wait
            log("l'appli ne tourne plus : relance" + (f" dans {wait} s" if wait else ""))
        if now < self.next_try and not fixed:
            return None
        self.spawn(["--reloaded"])
        self.launches.append(now)
        self.absent, self.next_try, self.fixed = 0, 0.0, False
        log("appli relancée" + (" (code modifié)" if fixed else ""))
        return "launch"


def main():
    mutex = _k32.CreateMutexW(None, False, instance.GUARD_MUTEX)
    if ctypes.get_last_error() == instance.ERROR_ALREADY_EXISTS:
        return 0                            # un gardien tourne déjà
    stop = _k32.CreateEventW(None, True, False, instance.GUARD_STOP)
    _k32.ResetEvent(stop)
    guard = Guard()
    own = _own_files()
    log(f"démarré (pid {os.getpid()})")
    try:
        while True:
            time.sleep(PERIOD)
            requested = _k32.WaitForSingleObject(stop, 0) == 0
            if requested and guard.running():
                _k32.ResetEvent(stop)       # relancée depuis (utilitaire « Redémarrer »)
                requested = False
            if guard.check(requested) == "stop":
                log("appli quittée, arrêt du gardien")
                return 0
            if _own_files() != own:         # gardien mis à jour : la nouvelle version prend
                log("code du gardien modifié, relance du gardien")
                _k32.CloseHandle(mutex)
                mutex = None
                instance._popen(["-m", "g19.guard"])
                return 0
    finally:
        for h in (stop, mutex):
            if h:
                _k32.CloseHandle(h)


if __name__ == "__main__":
    os._exit(main() or 0)
