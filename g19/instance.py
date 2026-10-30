"""Instance unique, arrêt à distance et relance de l'appli."""
import ctypes
import os
import subprocess
import sys
import threading
import time
from ctypes import wintypes
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent.parent
MAIN = APP_DIR / "g19_monitor.py"
MUTEX = "Local\\G19PCMonitor"
QUIT_EVENT = "Local\\G19PCMonitorQuit"
GUARD_MUTEX = "Local\\G19PCMonitorGuard"         # gardien qui relance l'appli si elle plante
GUARD_STOP = "Local\\G19PCMonitorGuardStop"      # posé par l'appli quand on la quitte exprès

ERROR_ALREADY_EXISTS = 183
SYNCHRONIZE = 0x00100000
EVENT_MODIFY_STATE = 0x0002

_k32 = ctypes.WinDLL("kernel32", use_last_error=True)
for _fn, _args in {"CreateMutexW": [wintypes.LPVOID, wintypes.BOOL, wintypes.LPCWSTR],
                   "OpenMutexW": [wintypes.DWORD, wintypes.BOOL, wintypes.LPCWSTR],
                   "CreateEventW": [wintypes.LPVOID, wintypes.BOOL, wintypes.BOOL, wintypes.LPCWSTR],
                   "OpenEventW": [wintypes.DWORD, wintypes.BOOL, wintypes.LPCWSTR]}.items():
    getattr(_k32, _fn).argtypes = _args
    getattr(_k32, _fn).restype = wintypes.HANDLE
_k32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
_k32.OpenProcess.restype = wintypes.HANDLE
_k32.SetEvent.argtypes = _k32.ResetEvent.argtypes = _k32.CloseHandle.argtypes = [wintypes.HANDLE]
_k32.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]


class SingleInstance:
    """Tient le mutex nommé tant que l'appli tourne ; expose la demande d'arrêt."""

    def __init__(self):
        self.mutex = _k32.CreateMutexW(None, False, MUTEX)
        self.already_running = ctypes.get_last_error() == ERROR_ALREADY_EXISTS
        self.event = _k32.CreateEventW(None, True, False, QUIT_EVENT)
        if not self.already_running:
            _k32.ResetEvent(self.event)

    def quit_requested(self):
        return _k32.WaitForSingleObject(self.event, 0) == 0

    def release(self):
        for h in (self.event, self.mutex):
            if h:
                _k32.CloseHandle(h)
        self.event = self.mutex = None


def is_running(name=MUTEX):
    h = _k32.OpenMutexW(SYNCHRONIZE, False, name)
    if h:
        _k32.CloseHandle(h)
    return bool(h)


def guard_running():
    return is_running(GUARD_MUTEX)


def ensure_guard():
    """Lance le gardien (g19/guard.py) s'il ne tourne pas : il relance l'appli si elle
    disparaît sans qu'on l'ait quittée (plantage d'un pilote, processus tué…)."""
    if guard_running() or os.environ.get("G19_NO_GUARD"):
        return False
    _popen(["-m", "g19.guard"])
    return True


def stopped_on_purpose():
    """L'appli s'arrête parce qu'on l'a quittée (icône, utilitaire, --stop) : le gardien ne
    doit pas la relancer, il s'arrête aussi."""
    h = _k32.OpenEventW(EVENT_MODIFY_STATE, False, GUARD_STOP)
    if h:
        _k32.SetEvent(h)
        _k32.CloseHandle(h)


def stop(timeout=10):
    """Demande à l'instance en cours de s'arrêter et attend qu'elle soit partie."""
    h = _k32.OpenEventW(EVENT_MODIFY_STATE, False, QUIT_EVENT)
    if not h:
        return not is_running()
    _k32.SetEvent(h)
    _k32.CloseHandle(h)
    end = time.time() + timeout
    while is_running() and time.time() < end:
        time.sleep(0.2)
    return not is_running()


def wait_exit(pid, timeout=15):
    """Attend la fin du processus `pid` (au plus `timeout` s)."""
    h = _k32.OpenProcess(SYNCHRONIZE, False, pid)
    if h:
        _k32.WaitForSingleObject(h, int(timeout * 1000))
        _k32.CloseHandle(h)


def spawn(args=(), wait_pid=None):
    """Lance l'appli en arrière-plan, sans console ; `wait_pid` : la nouvelle instance attend
    d'abord la fin de ce processus."""
    env = {**os.environ, "G19_WAIT_PID": str(wait_pid)} if wait_pid else None
    _popen([str(MAIN), *args], env)


def _popen(args, env=None):
    exe = Path(sys.executable)
    pythonw = exe.with_name("pythonw.exe")
    flags = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
    subprocess.Popen([str(pythonw if pythonw.exists() else exe), *args],
                     cwd=APP_DIR, creationflags=flags, close_fds=True, env=env,
                     stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


class SourceWatcher:
    """Détecte une modification du code de l'appli (g19_monitor.py et g19/*.py).

    `background` : les fichiers sont relus dans un fil à part, chaque seconde ; un disque qui
    tarde à répondre (mise en veille, antivirus) ne fige plus la boucle de l'écran."""

    def __init__(self, background=False):
        self.mtimes = self._scan()
        self._pending = set()
        self._lock = threading.Lock()
        if background:
            threading.Thread(target=self._run, daemon=True, name="sources").start()
        self.background = background

    @staticmethod
    def _scan():
        files = [MAIN, *sorted((APP_DIR / "g19").glob("*.py"))]
        out = {}
        for p in files:
            try:
                out[p] = p.stat().st_mtime
            except OSError:
                pass        # supprimé entre-temps (mise à jour, changement de branche)
        return out

    def _diff(self):
        now = self._scan()
        changed = {p for p in now.keys() | self.mtimes.keys() if self.mtimes.get(p) != now.get(p)}
        self.mtimes = now
        return changed

    def _run(self):
        while True:
            time.sleep(1)
            try:
                changed = self._diff()
            except Exception:
                continue
            if changed:
                with self._lock:
                    self._pending |= changed

    def changed(self):
        """Fichiers modifiés depuis le dernier appel (vide si rien)."""
        if not self.background:
            return sorted(self._diff())
        with self._lock:
            out, self._pending = sorted(self._pending), set()
        return out
