"""Instance unique, arrêt à distance et relance, version Linux (g19/instance.py s'en sert à la
place des mutex et événements nommés de Windows).

  - instance unique : verrou flock sur un fichier (libéré par le noyau si l'appli plante) ;
  - arrêt demandé : un fichier « …quit » posé par --stop, ou SIGTERM / SIGINT ;
  - relance : nouveau processus détaché (sa propre session), sorties dans le vide.
Fichiers dans $XDG_RUNTIME_DIR (sinon /tmp), un par nom de mutex Windows."""
import fcntl
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

RUN_DIR = Path(os.environ.get("XDG_RUNTIME_DIR") or "/tmp") / "g19-monitor"


def _path(name, suffix):
    RUN_DIR.mkdir(parents=True, exist_ok=True)
    return RUN_DIR / (name.split("\\")[-1] + suffix)


class SingleInstance:
    """Tient le verrou tant que l'appli tourne ; expose la demande d'arrêt."""

    def __init__(self, mutex, quit_event):
        self._quit = _path(quit_event, ".quit")
        self._f = open(_path(mutex, ".lock"), "a+")
        try:
            fcntl.flock(self._f, fcntl.LOCK_EX | fcntl.LOCK_NB)
            self.already_running = False
        except OSError:
            self.already_running = True
        self._signal = False
        if not self.already_running:
            self._quit.unlink(missing_ok=True)
            self._f.seek(0)
            self._f.truncate()
            self._f.write(str(os.getpid()))
            self._f.flush()
            for sig in (signal.SIGTERM, signal.SIGINT):
                try:
                    signal.signal(sig, self._on_signal)
                except ValueError:          # pas dans le fil principal
                    pass

    def _on_signal(self, *_):
        self._signal = True

    def quit_requested(self):
        return self._signal or self._quit.exists()

    def release(self):
        if self._f:
            if not self.already_running:
                self._quit.unlink(missing_ok=True)
            try:
                fcntl.flock(self._f, fcntl.LOCK_UN)
            except OSError:
                pass
            self._f.close()
            self._f = None


def is_running(name):
    try:
        with open(_path(name, ".lock"), "a+") as f:
            fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
            fcntl.flock(f, fcntl.LOCK_UN)
        return False
    except OSError:
        return True


def stop(timeout, mutex, quit_event):
    """Demande à l'instance en cours de s'arrêter et attend qu'elle soit partie."""
    if not is_running(mutex):
        return True
    _path(quit_event, ".quit").touch()
    end = time.time() + timeout
    while is_running(mutex) and time.time() < end:
        time.sleep(0.2)
    return not is_running(mutex)


def stopped_on_purpose(event):
    _path(event, ".stopped").touch()


def wait_exit(pid, timeout=15):
    end = time.time() + timeout
    while time.time() < end:
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return
        except PermissionError:
            pass
        time.sleep(0.1)


def in_service():
    """Lancée par le service systemd du gardien (g19-monitor.service) ? INVOCATION_ID ne suffit
    pas : Plasma lance terminal et applis sous systemd, elles en héritent."""
    try:
        with open("/proc/self/cgroup") as f:
            return "/g19-monitor.service" in f.read()
    except OSError:
        return False


def _reap_children():
    """Enfants (pactl, busctl…) arrêtés et ramassés : pas de zombies après execve."""
    import psutil
    kids = psutil.Process().children()
    for k in kids:
        try:
            k.terminate()
        except psutil.Error:
            pass
    psutil.wait_procs(kids, timeout=2)


def popen(args, cwd, env=None):
    if in_service() and args and str(args[0]).endswith("g19_monitor.py"):
        # lancée par le gardien (systemd) : relance en place, même processus pour le service
        env = dict(env or os.environ)
        env.pop("G19_WAIT_PID", None)
        import logging
        logging.shutdown()
        _reap_children()
        os.chdir(cwd)
        os.execve(sys.executable, [sys.executable, *map(str, args)], env)
    subprocess.Popen([sys.executable, *args], cwd=cwd, env=env, start_new_session=True,
                     close_fds=True, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                     stderr=subprocess.DEVNULL)
