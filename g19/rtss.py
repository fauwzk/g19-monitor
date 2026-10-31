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
           "firefox.exe", "discord.exe", "spotify.exe", "steamwebhelper.exe", "obs64.exe",
           # lecteurs vidéo : en plein écran, le pilote peut leur compter des images
           "vlc.exe", "mpv.exe", "mpc-hc64.exe", "mpc-be64.exe", "potplayermini64.exe",
           "wmplayer.exe", "applicationframehost.exe", "powerpnt.exe"}
# liste de l'utilisateur (réglage game_blacklist) : débuts de noms d'exécutable sans « .exe »,
# « obs » couvre obs64, obs32, obs-browser-page…
USER_IGNORED = ()


def blacklist_key(name):
    """« OBS64.exe » → « obs64 » : la forme comparée à la liste de l'utilisateur."""
    name = (name or "").strip().lower().replace("\\", "/").rsplit("/", 1)[-1]
    return name[:-4] if name.endswith(".exe") else name


def set_blacklist(items):
    global USER_IGNORED
    USER_IGNORED = tuple(k for k in (blacklist_key(i) for i in items or ()) if k)


def ignored(name):
    low = (name or "").lower()
    return low in IGNORED or blacklist_key(low).startswith(USER_IGNORED or ("\0",))


def current_game(fps_probe=None):
    """L'appli au premier plan si RTSS la mesure, sinon le jeu le plus récemment actif ;
    à défaut (RTSS absent ou désactivé pour ce jeu), le jeu en plein écran au premier plan,
    sans FPS. `fps_probe` : FPS mesurés par le pilote, pour reconnaître aussi les jeux installés
    hors des launchers."""
    live = []
    apps = read_apps()
    if apps:
        now = _k32.GetTickCount()
        live = [a for a in apps if (now - a["tick"]) & 0xFFFFFFFF < STALE_MS
                and not ignored(a["name"])]
    if not live:
        return window_game(fps_probe)
    fg = _foreground_pid()
    for a in live:
        if a["pid"] == fg:
            return a
    return max(live, key=lambda a: a["tick"])


# --- détection sans RTSS : fenêtre plein écran d'un jeu ---------------------------------------

# dossiers d'installation des launchers (chemins en minuscules, séparateurs « / »)
GAME_DIRS = ("/steamapps/common/", "/epic games/", "/riot games/", "/gog galaxy/games/",
             "/ubisoft game launcher/games/", "/ea games/", "/electronic arts/",
             "/xboxgames/", "/battle.net/", "/blizzard entertainment/")
GAME_EXES = {"cs2", "valorant-win64-shipping", "league of legends", "r5apex",
             "fortniteclient-win64-shipping", "rocketleague", "overwatch", "gta5",
             "eldenring", "javaw", "rainbowsix", "rainbowsix_be"}

_u32.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
_u32.MonitorFromWindow.restype = wintypes.HMONITOR
_u32.MonitorFromWindow.argtypes = [wintypes.HWND, wintypes.DWORD]
_u32.IsWindow.argtypes = [wintypes.HWND]
_u32.IsIconic.argtypes = [wintypes.HWND]


class _MonitorInfo(ctypes.Structure):
    _fields_ = [("cbSize", wintypes.DWORD), ("rcMonitor", wintypes.RECT),
                ("rcWork", wintypes.RECT), ("dwFlags", wintypes.DWORD)]


_u32.GetMonitorInfoW.argtypes = [wintypes.HMONITOR, ctypes.POINTER(_MonitorInfo)]

_paths = {}            # pid → chemin de l'exécutable (le plus coûteux à lire)
_window = None         # dernier jeu trouvé ainsi : {"pid", "path", "name", "hwnd", …}


def _exe_path(pid):
    if pid not in _paths:
        try:
            import psutil
            _paths[pid] = psutil.Process(pid).exe()
        except Exception:
            _paths[pid] = ""
        if len(_paths) > 64:
            _paths.pop(next(iter(_paths)))
    return _paths[pid]


def _fullscreen(hwnd):
    """La fenêtre couvre-t-elle tout son écran (plein écran exclusif ou fenêtré sans bord) ?"""
    r = wintypes.RECT()
    if not _u32.GetWindowRect(hwnd, ctypes.byref(r)):
        return False
    mi = _MonitorInfo(cbSize=ctypes.sizeof(_MonitorInfo))
    if not _u32.GetMonitorInfoW(_u32.MonitorFromWindow(hwnd, 2), ctypes.byref(mi)):
        return False
    m = mi.rcMonitor
    return r.left <= m.left and r.top <= m.top and r.right >= m.right and r.bottom >= m.bottom


def _rendering(path, fps_probe):
    """Appli plein écran hors launcher : jeu si le pilote lui compte des images."""
    low = path.lower().replace("\\", "/")
    if not low.endswith(".exe") or ignored(low.rsplit("/", 1)[-1]) or "/windows/" in low:
        return False
    try:
        return bool(fps_probe())
    except Exception:
        return False


def looks_like_game(path):
    low = path.lower().replace("\\", "/")
    if not low.endswith(".exe") or ignored(low.rsplit("/", 1)[-1]):
        return False
    return any(d in low for d in GAME_DIRS) or blacklist_key(low) in GAME_EXES


def window_game(fps_probe=None):
    """Jeu détecté sans RTSS : fenêtre au premier plan en plein écran, d'un exécutable installé
    par un launcher (ou connu), ou de n'importe quelle appli dont le pilote mesure les images
    (`fps_probe`, hors Windows et liste d'exclusion). Il reste détecté pendant un alt-tab tant que
    sa fenêtre existe et n'est pas réduite. FPS laissés à l'appelant : fps = None."""
    global _window
    hwnd = _u32.GetForegroundWindow()
    if hwnd and _fullscreen(hwnd):
        pid = _foreground_pid()
        path = _exe_path(pid) if pid else ""
        if path and (looks_like_game(path) or (fps_probe and _rendering(path, fps_probe))):
            if not _window or _window["pid"] != pid:
                _window = {"pid": pid, "path": path,
                           "name": path.replace("\\", "/").rsplit("/", 1)[-1],
                           "fps": None, "frametime_ms": None, "hwnd": hwnd}
            return _window
    w = _window
    if w and _u32.IsWindow(w["hwnd"]) and not _u32.IsIconic(w["hwnd"]) and not ignored(w["name"]):
        return w
    _window = None
    return None


if __name__ == "__main__":
    for a in read_apps() or []:
        print(a)
    print("jeu :", current_game())
