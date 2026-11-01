"""Gardien des applis : lance celle qui correspond à chaque clavier branché et la relance si
elle disparaît sans qu'on l'ait quittée.

Lancé par les applis elles-mêmes (instance.ensure_guard), il tourne à part, sans console :

    pythonw -m g19.guard

Deux applis : G19 Monitor (écran couleur du G19) et G15 Monitor (écran monochrome des G15,
G510 et G13). Le gardien regarde quels claviers sont branchés (keyboards.py) :
- quand un clavier est branché, il lance aussitôt l'appli qui lui correspond (au démarrage
  du gardien : celle d'un clavier présent, après les vérifications habituelles) ;
- une appli qui disparaît (exception, plantage dans un pilote, processus tué) est relancée,
  si son clavier est toujours là ; relances espacées si elle replante aussitôt, tout de
  suite quand le code change (une correction après un plantage) ;
- une appli quittée exprès (icône, utilitaire, --stop) pose son événement d'arrêt : elle
  n'est plus relancée, jusqu'à ce que son clavier soit rebranché ou qu'on la relance.
G15 Monitor n'est géré qu'une fois lancé une première fois (ses réglages existent) et si son
option « Lancer au branchement du clavier » est active. Sans hidapi (claviers non
détectables), il ne garde que l'appli G19, comme avant.

Le chien de garde interne de l'appli (Watchdog) couvre une boucle figée ; ici, c'est le
processus qui meurt."""
import ctypes
import os
import time
from pathlib import Path

from . import config, instance, keyboards
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
    files = (HERE, HERE.with_name("instance.py"), HERE.with_name("keyboards.py"))
    return {p: p.stat().st_mtime for p in files if p.exists()}


class Guard:
    """Une appli surveillée : relance après disparition (avec espacement)."""

    def __init__(self, running=instance.is_running,
                 spawn=lambda reloaded: instance.spawn(["--reloaded"] if reloaded else []),
                 sources=None, clock=time.time, name="l'appli"):
        self.running, self.spawn, self.clock = running, spawn, clock
        self.sources = sources or instance.SourceWatcher()
        self.name = name
        self.absent = 0
        self.fixed = False          # code modifié depuis la disparition de l'appli
        self.launches = []          # heures des relances (fenêtre de WINDOW s)
        self.next_try = 0.0

    def delay(self, now):
        self.launches = [t for t in self.launches if now - t < WINDOW]
        return BACKOFF[min(len(self.launches), len(BACKOFF) - 1)]

    def launch_now(self, why):
        """Lancement immédiat (clavier qui vient d'être branché)."""
        self.spawn(False)
        self.absent, self.next_try, self.fixed = 0, 0.0, False
        log(f"{self.name} lancée ({why})")

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
            log(f"{self.name} ne tourne plus : relance" + (f" dans {wait} s" if wait else ""))
        if now < self.next_try and not fixed:
            return None
        self.spawn(True)                      # relance : écran de démarrage court
        self.launches.append(now)
        self.absent, self.next_try, self.fixed = 0, 0.0, False
        log(f"{self.name} relancée" + (" (code modifié)" if fixed else ""))
        return "launch"


class Watched:
    """Une appli, son clavier et son événement « quittée exprès »."""

    def __init__(self, guard, kind, stop_event, fallback_present, enabled=lambda: True):
        self.guard, self.kind, self.stop_event = guard, kind, stop_event
        self.enabled = enabled      # réglage : le gardien s'occupe-t-il de cette appli ?
        self.fallback_present = fallback_present    # sans détection des claviers
        self.stopped = False        # quittée exprès : pas de relance avant un rebranchement
        self.present = None         # clavier branché au passage précédent (None : premier)

    def step(self, kb):
        """Un passage avec l'état des claviers (ou None si inconnu)."""
        g = self.guard
        present = self.fallback_present if kb is None else kb[self.kind]
        if not self.enabled():
            present = False
        requested = _k32.WaitForSingleObject(self.stop_event, 0) == 0
        if requested:
            _k32.ResetEvent(self.stop_event)
            if g.running():
                requested = False           # relancée depuis (utilitaire « Redémarrer »)
            else:
                self.stopped = True
                log(f"{g.name} quittée exprès : pas de relance avant un rebranchement")
        if g.running():
            self.stopped = False
        first = self.present is None
        plugged = present and self.present is not True and kb is not None
        self.present = present
        if plugged and not first and not g.running():
            # clavier qui vient d'être branché : son appli tout de suite (au démarrage du
            # gardien, une appli peut être en train de se relancer : vérifications normales)
            self.stopped = False
            g.launch_now("clavier branché")
            return
        if not present:
            g.absent, g.next_try = 0, 0.0    # pas de clavier : rien à relancer
            return
        g.check(self.stopped)


def mono_enabled():
    """G15 Monitor n'est lancé par le gardien qu'une fois utilisé (ses réglages existent) et
    si l'option « lancer au branchement » n'est pas coupée."""
    data = config.load("g15_settings.json", None)
    return isinstance(data, dict) and data.get("auto_launch", True)


def main():
    mutex = _k32.CreateMutexW(None, False, instance.GUARD_MUTEX)
    if ctypes.get_last_error() == instance.ERROR_ALREADY_EXISTS:
        return 0                            # un gardien tourne déjà
    stop19 = _k32.CreateEventW(None, True, False, instance.GUARD_STOP)
    stop15 = _k32.CreateEventW(None, True, False, instance.MONO_GUARD_STOP)
    for h in (stop19, stop15):
        _k32.ResetEvent(h)
    apps = [
        Watched(Guard(name="G19 Monitor"), "color", stop19, fallback_present=True),
        Watched(Guard(running=lambda: instance.is_running(instance.MONO_MUTEX),
                      spawn=lambda reloaded: instance._popen([str(instance.MONO_MAIN)]),
                      sources=instance.SourceWatcher(main=instance.MONO_MAIN),
                      name="G15 Monitor"), "mono", stop15, fallback_present=False,
                enabled=mono_enabled),
    ]
    own = _own_files()
    log(f"démarré (pid {os.getpid()})")
    try:
        while True:
            kb = keyboards.detect()
            for app in apps:
                try:
                    app.step(kb)
                except Exception as e:
                    log(f"{app.guard.name} : {e.__class__.__name__}: {e}")
            if _own_files() != own:         # gardien mis à jour : la nouvelle version prend
                log("code du gardien modifié, relance du gardien")
                _k32.CloseHandle(mutex)
                mutex = None
                instance._popen(["-m", "g19.guard"])
                return 0
            time.sleep(PERIOD)
    finally:
        for h in (stop19, stop15, mutex):
            if h:
                _k32.CloseHandle(h)


if __name__ == "__main__":
    os._exit(main() or 0)
