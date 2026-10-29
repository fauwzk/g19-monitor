"""FPS / frametime depuis la mémoire partagée de RivaTuner Statistics Server (« RTSSSharedMemoryV2 »)."""
import ctypes
import struct
from ctypes import wintypes

from .afterburner import FILE_MAP_READ, _k32, _cstr

SIGNATURE = 0x52545353  # 'RTSS'
_HEADER = struct.Struct("<5I")  # signature, version, appEntrySize, appArrOffset, appArrSize
_APP = struct.Struct("<I260sIIIII")  # pid, name, flags, time0, time1, frames, frameTime (µs)

_u32 = ctypes.WinDLL("user32")
_u32.GetForegroundWindow.restype = wintypes.HWND
_u32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]


def _foreground_pid():
    pid = wintypes.DWORD(0)
    _u32.GetWindowThreadProcessId(_u32.GetForegroundWindow(), ctypes.byref(pid))
    return pid.value


def read_apps():
    """Liste de dicts {pid, name, fps, frametime_ms, tick} pour les applis 3D hookées par RTSS."""
    h = _k32.OpenFileMappingW(FILE_MAP_READ, False, "RTSSSharedMemoryV2")
    if not h:
        return None
    try:
        view = _k32.MapViewOfFile(h, FILE_MAP_READ, 0, 0, 0)
        if not view:
            return None
        try:
            sig, ver, esize, off, count = _HEADER.unpack(ctypes.string_at(view, _HEADER.size))
            if sig != SIGNATURE or count > 1024 or esize < _APP.size:
                return None
            raw = ctypes.string_at(view + off, count * esize)
        finally:
            _k32.UnmapViewOfFile(view)
    finally:
        _k32.CloseHandle(h)

    apps = []
    for i in range(count):
        pid, name, _flags, t0, t1, frames, ft = _APP.unpack_from(raw, i * esize)
        if not pid or t1 <= t0:
            continue
        path = _cstr(name)
        apps.append({
            "pid": pid,
            "path": path,
            "name": path.replace("\\", "/").rsplit("/", 1)[-1],
            "fps": 1000.0 * frames / (t1 - t0),
            "frametime_ms": ft / 1000.0,
            "tick": t1,
            "slot": off + i * esize,
        })
    return apps


def frametime(game):
    """Temps de la dernière image (ms) du jeu `game` (de current_game), lu sans copier toute
    la mémoire partagée : assez léger pour chaque image du G19. None si le jeu a disparu."""
    h = _k32.OpenFileMappingW(FILE_MAP_READ, False, "RTSSSharedMemoryV2")
    if not h:
        return None
    try:
        view = _k32.MapViewOfFile(h, FILE_MAP_READ, 0, 0, game["slot"] + _APP.size)
        if not view:
            return None
        try:
            pid, _n, _f, _t0, _t1, _fr, ft = _APP.unpack(ctypes.string_at(view + game["slot"],
                                                                          _APP.size))
        finally:
            _k32.UnmapViewOfFile(view)
    finally:
        _k32.CloseHandle(h)
    if pid != game["pid"] or not ft:
        return None
    return ft / 1000.0


_k32.GetTickCount.restype = wintypes.DWORD
STALE_MS = 1500
# applis de bureau que RTSS hooke aussi mais qui ne sont pas des jeux
IGNORED = {"parsecd.exe", "claude.exe", "explorer.exe", "dwm.exe", "chrome.exe", "msedge.exe",
           "firefox.exe", "discord.exe", "spotify.exe", "steamwebhelper.exe", "obs64.exe"}


def current_game():
    """L'appli au premier plan si RTSS la mesure, sinon le jeu le plus récemment actif."""
    apps = read_apps()
    if not apps:
        return None
    now = _k32.GetTickCount()
    live = [a for a in apps if (now - a["tick"]) & 0xFFFFFFFF < STALE_MS
            and a["name"].lower() not in IGNORED]
    if not live:
        return None
    fg = _foreground_pid()
    for a in live:
        if a["pid"] == fg:
            return a
    return max(live, key=lambda a: a["tick"])


if __name__ == "__main__":
    for a in read_apps() or []:
        print(a)
