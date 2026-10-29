"""Bibliothèque Steam locale : jeux installés, temps de jeu, pochettes en cache."""
import re
import time
import winreg
from pathlib import Path


def parse_vdf(text):
    """Parseur minimal du format texte KeyValues de Valve."""
    root = {}
    stack, key = [root], None
    for quoted, brace in re.findall(r'"((?:[^"\\]|\\.)*)"|([{}])', text):
        if brace == "{":
            child = {}
            stack[-1][key] = child
            stack.append(child)
            key = None
        elif brace == "}":
            if len(stack) > 1:
                stack.pop()
        elif key is None:
            key = quoted
        else:
            stack[-1][key] = quoted.replace("\\\\", "\\")
            key = None
    return root


def ci(d, *keys):
    """Accès imbriqué insensible à la casse."""
    for k in keys:
        if not isinstance(d, dict):
            return None
        d = next((v for kk, v in d.items() if kk.lower() == k.lower()), None)
    return d


def steam_root():
    try:
        k = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Valve\Steam")
        return Path(winreg.QueryValueEx(k, "SteamPath")[0])
    except OSError:
        return None


class SteamLibrary:
    def __init__(self):
        self.root = steam_root()
        self.apps = {}          # appid → nom
        self.dirs = {}          # chemin du dossier d'install (minuscules) → appid
        self._playtime = {}     # appid → (minutes, last_played)
        self._lc_mtime = 0
        if self.root:
            self._scan()

    def _scan(self):
        libs = ci(parse_vdf(self._read(self.root / "steamapps" / "libraryfolders.vdf")),
                  "libraryfolders") or {}
        paths = {self.root} | {Path(v["path"]) for v in libs.values()
                               if isinstance(v, dict) and v.get("path")}
        for lib in paths:
            for acf in (lib / "steamapps").glob("appmanifest_*.acf"):
                st = ci(parse_vdf(self._read(acf)), "AppState") or {}
                appid, name, inst = st.get("appid"), st.get("name"), st.get("installdir")
                if appid and inst:
                    self.apps[appid] = name or inst
                    common = lib / "steamapps" / "common" / inst
                    self.dirs[str(common).lower()] = appid

    @staticmethod
    def _read(path):
        try:
            return path.read_text("utf-8", errors="replace")
        except OSError:
            return ""

    def find_app(self, exe_path):
        p = exe_path.lower().replace("/", "\\")
        for d, appid in self.dirs.items():
            if p.startswith(d + "\\"):
                return appid
        return None

    def playtime(self, appid):
        """(minutes totales, dernier lancement) d'après localconfig.vdf du compte le plus récent."""
        if not self.root:
            return None
        configs = list((self.root / "userdata").glob("*/config/localconfig.vdf"))
        if not configs:
            return None
        lc = max(configs, key=lambda p: p.stat().st_mtime)
        mtime = lc.stat().st_mtime
        if mtime != self._lc_mtime:
            self._lc_mtime = mtime
            apps = ci(parse_vdf(self._read(lc)), "UserLocalConfigStore", "Software", "Valve",
                      "Steam", "apps") or {}
            self._playtime = {
                a: (int(v.get("Playtime", 0) or 0), int(v.get("LastPlayed", 0) or 0))
                for a, v in apps.items() if isinstance(v, dict)}
        return self._playtime.get(str(appid))

    def image(self, appid, kind="library_600x900"):
        """Chemin d'une image du cache Steam (library_600x900, library_hero_blur, header…)."""
        if not self.root:
            return None
        cache = self.root / "appcache" / "librarycache"
        for cand in (cache / str(appid) / f"{kind}.jpg", cache / f"{appid}_{kind}.jpg"):
            if cand.exists():
                return cand
        found = next((cache / str(appid)).glob(f"**/{kind}*.jpg"), None)
        return found


if __name__ == "__main__":
    t = time.time()
    lib = SteamLibrary()
    print(f"{len(lib.apps)} jeux en {time.time() - t:.2f}s")
    for appid, name in list(lib.apps.items())[:8]:
        print(appid, name, lib.playtime(appid), lib.image(appid))
