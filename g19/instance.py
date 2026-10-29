"""Instance unique, arrêt à distance et relance de l'appli."""
import ctypes
import subprocess
import sys
import time
from ctypes import wintypes
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent.parent
MAIN = APP_DIR / "g19_monitor.py"
MUTEX = "Local\\G19PCMonitor"
QUIT_EVENT = "Local\\G19PCMonitorQuit"

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


def is_running():
    h = _k32.OpenMutexW(SYNCHRONIZE, False, MUTEX)
    if h:
        _k32.CloseHandle(h)
    return bool(h)


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
    import os
    env = {**os.environ, "G19_WAIT_PID": str(wait_pid)} if wait_pid else None
    exe = Path(sys.executable)
    pythonw = exe.with_name("pythonw.exe")
    flags = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
    subprocess.Popen([str(pythonw if pythonw.exists() else exe), str(MAIN), *args],
                     cwd=APP_DIR, creationflags=flags, close_fds=True, env=env,
                     stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


class SourceWatcher:
    """Détecte une modification du code de l'appli (g19_monitor.py et g19/*.py)."""

    def __init__(self):
        self.mtimes = self._scan()

    @staticmethod
    def _scan():
        files = [MAIN, *sorted((APP_DIR / "g19").glob("*.py"))]
        return {p: p.stat().st_mtime for p in files if p.exists()}

    def changed(self):
        """Fichiers modifiés depuis le dernier appel (vide si rien)."""
        now = self._scan()
        changed = [p for p, m in now.items() if self.mtimes.get(p) != m]
        self.mtimes = now
        return changed
