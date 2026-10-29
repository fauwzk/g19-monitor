"""Identifie un jeu à partir de son exécutable, quel que soit le launcher : Steam, Epic,
Xbox/Game Pass, et tout ce qui s'enregistre dans « Programmes et fonctionnalités »
(Ubisoft, EA, Riot, Battle.net, GOG, Rockstar…). En dernier recours : les infos de version
de l'exe, puis son nom de fichier."""
import ctypes
import json
import re
import threading
import winreg
from ctypes import wintypes
from pathlib import Path

from .steam import SteamLibrary

EPIC_MANIFESTS = Path(r"C:\ProgramData\Epic\EpicGamesLauncher\Data\Manifests")
UNINSTALL_KEYS = [
    (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall"),
    (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall"),
    (winreg.HKEY_CURRENT_USER, r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall"),
]
# éditeur / chemin → launcher affiché
LAUNCHERS = [
    (r"ubisoft", "Ubisoft"), (r"electronic arts|ea games|\bea app", "EA"),
    (r"riot", "Riot"), (r"blizzard|battle\.net", "Battle.net"), (r"gog", "GOG"),
    (r"rockstar", "Rockstar"), (r"epic games", "Epic"), (r"bethesda", "Bethesda"),
]
NOT_GAMES = re.compile(r"launcher|client|vanguard|redistributable|runtime|driver|sdk|"
                       r"development kit|anticheat|easyanticheat|battleye", re.I)


def clean_name(name):
    return re.sub(r"\s+", " ", re.sub(r"[™®©]", "", name or "")).strip()


def launcher_of(*texts):
    blob = " ".join(t for t in texts if t).lower()
    return next((label for pattern, label in LAUNCHERS if re.search(pattern, blob)), None)


# --- infos de version d'un exe (ProductName / FileDescription) ---------------------------------

_ver = ctypes.WinDLL("version")
_ver.GetFileVersionInfoSizeW.argtypes = [wintypes.LPCWSTR, ctypes.POINTER(wintypes.DWORD)]
_ver.GetFileVersionInfoW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD,
                                     ctypes.c_void_p]
_ver.VerQueryValueW.argtypes = [ctypes.c_void_p, wintypes.LPCWSTR, ctypes.POINTER(ctypes.c_void_p),
                                ctypes.POINTER(wintypes.UINT)]


def exe_product_name(path):
    try:
        size = _ver.GetFileVersionInfoSizeW(path, None)
        if not size:
            return None
        buf = ctypes.create_string_buffer(size)
        if not _ver.GetFileVersionInfoW(path, 0, size, buf):
            return None
        ptr, n = ctypes.c_void_p(), wintypes.UINT()
        if not _ver.VerQueryValueW(buf, r"\VarFileInfo\Translation", ctypes.byref(ptr), ctypes.byref(n)):
            return None
        lang, cp = ctypes.cast(ptr, ctypes.POINTER(wintypes.WORD * 2)).contents
        for field in ("ProductName", "FileDescription"):
            q = rf"\StringFileInfo\{lang:04x}{cp:04x}\{field}"
            if _ver.VerQueryValueW(buf, q, ctypes.byref(ptr), ctypes.byref(n)) and n.value > 1:
                value = clean_name(ctypes.wstring_at(ptr, n.value - 1))
                if value and not re.search(r"unreal|unity|engine|launcher|bootstrap", value, re.I):
                    return value
    except OSError:
        pass
    return None


# --- catalogue -----------------------------------------------------------------------------------

class GameCatalog:
    def __init__(self):
        self.steam = None
        self.installs = []   # (dossier en minuscules, nom, launcher), du plus long au plus court
        self.ready = threading.Event()
        threading.Thread(target=self._scan, daemon=True).start()

    def _scan(self):
        try:
            self.steam = SteamLibrary()
        except Exception:
            self.steam = None
        installs = []
        try:
            installs += self._epic()
        except Exception:
            pass
        try:
            installs += self._uninstall_entries()
        except Exception:
            pass
        self.installs = sorted(installs, key=lambda e: -len(e[0]))
        self.ready.set()

    @staticmethod
    def _epic():
        out = []
        for item in EPIC_MANIFESTS.glob("*.item"):
            data = json.loads(item.read_text("utf-8", errors="replace"))
            if data.get("InstallLocation") and data.get("DisplayName"):
                out.append((str(Path(data["InstallLocation"])).lower(),
                            clean_name(data["DisplayName"]), "Epic"))
        return out

    @staticmethod
    def _uninstall_entries():
        out = []
        for hive, path in UNINSTALL_KEYS:
            try:
                root = winreg.OpenKey(hive, path)
            except OSError:
                continue
            for i in range(winreg.QueryInfoKey(root)[0]):
                try:
                    sub = winreg.OpenKey(root, winreg.EnumKey(root, i))
                    name = winreg.QueryValueEx(sub, "DisplayName")[0]
                    loc = winreg.QueryValueEx(sub, "InstallLocation")[0]
                except OSError:
                    continue
                try:
                    publisher = winreg.QueryValueEx(sub, "Publisher")[0]
                except OSError:
                    publisher = ""
                loc = str(Path(loc.strip().strip('"'))).lower() if loc and loc.strip() else ""
                if len(loc) > 3 and name and not NOT_GAMES.search(name):
                    out.append((loc, clean_name(name), launcher_of(publisher, loc)))
        return out

    def identify(self, exe_path, exe_name):
        """{name, launcher, steam_appid} pour un exe de jeu."""
        self.ready.wait(5)
        p = str(Path(exe_path)).lower()
        if self.steam:
            appid = self.steam.find_app(exe_path)
            if appid:
                return {"name": clean_name(self.steam.apps.get(appid)), "launcher": "Steam",
                        "steam_appid": appid}
        for loc, name, launcher in self.installs:
            if p.startswith(loc + "\\"):
                return {"name": name, "launcher": launcher or launcher_of(p), "steam_appid": None}
        m = re.search(r"\\xboxgames\\([^\\]+)\\", p) or re.search(r"\\windowsapps\\([^_\\]+)", p)
        if m:
            folder = Path(exe_path).parts[[x.lower() for x in Path(exe_path).parts].index(m.group(1))]
            return {"name": clean_name(re.sub(r"(?<=[a-z])(?=[A-Z])", " ", folder)),
                    "launcher": "Xbox", "steam_appid": None}
        return {"name": exe_product_name(exe_path), "launcher": launcher_of(p),
                "steam_appid": None}


if __name__ == "__main__":
    import sys
    cat = GameCatalog()
    cat.ready.wait()
    print(len(cat.installs), "installs hors Steam")
    for exe in sys.argv[1:]:
        print(exe, "→", cat.identify(exe, Path(exe).name))
