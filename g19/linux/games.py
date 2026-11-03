"""Jeu en cours sous Linux : un processus lancé par Steam porte SteamAppId dans son
environnement (jeu natif ou jeu Windows via Proton) ; son nom vient du manifeste
appmanifest_<id>.acf des bibliothèques Steam. Pas de FPS (pas d'équivalent de RTSS sous
Linux) : fps None, comme un jeu vu sans RTSS sous Windows. Même forme de jeu que
rtss.current_game : {"name", "pid", "path", "fps", …}."""
import re
import time
from pathlib import Path

import psutil

SCAN_EVERY = 2.0
STEAM_ROOTS = [Path.home() / ".local/share/Steam", Path.home() / ".steam/steam",
               Path.home() / ".var/app/com.valvesoftware.Steam/.local/share/Steam"]
# outils de Steam / Proton qui portent aussi SteamAppId : pas le jeu lui-même
HELPERS = {"steam", "steamwebhelper", "reaper", "pressure-vessel", "pv-bwrap", "srt-bwrap",
           "wineserver", "wine", "wine64", "wine-preloader", "wine64-preloader", "python",
           "python3", "sh", "bash", "zsh", "steam-runtime-launcher-service", "proton",
           "services.exe", "winedevice.exe", "plugplay.exe", "explorer.exe", "rpcss.exe",
           "svchost.exe", "tabtip.exe", "conhost.exe", "start.exe", "steam.exe",
           "gameoverlayui", "steamerrorreporter", "crashpad_handler"}
_names = {}
_state = {"at": 0.0, "game": None}


def _libraries():
    libs = []
    for root in STEAM_ROOTS:
        vdf = root / "steamapps" / "libraryfolders.vdf"
        if vdf.exists():
            text = vdf.read_text("utf-8", "replace")
            libs += [Path(p) / "steamapps" for p in re.findall(r'"path"\s+"([^"]+)"', text)]
        if (root / "steamapps").is_dir():
            libs.append(root / "steamapps")
    return list(dict.fromkeys(libs))


def app_name(appid):
    if appid in _names:
        return _names[appid]
    name = None
    for lib in _libraries():
        acf = lib / f"appmanifest_{appid}.acf"
        try:
            m = re.search(r'"name"\s+"([^"]+)"', acf.read_text("utf-8", "replace"))
        except OSError:
            continue
        if m:
            name = m.group(1)
            break
    _names[appid] = name
    return name


def _scan():
    best = None
    for p in psutil.process_iter(["pid", "name", "create_time"]):
        name = (p.info["name"] or "").lower()
        if name in HELPERS:
            continue
        try:
            env = p.environ()
        except (psutil.Error, OSError):
            continue
        appid = env.get("SteamAppId") or env.get("SteamGameId")
        if not appid or not appid.isdigit() or appid == "0":
            continue
        # le plus ancien processus non-outil de ce jeu : son exécutable principal
        if best is None or p.info["create_time"] < best[2]:
            best = (p, appid, p.info["create_time"])
    if not best:
        return None
    p, appid, _ = best
    name = app_name(appid) or p.info["name"]
    return {"name": name, "pid": p.info["pid"], "path": f"steam:{appid}", "fps": None,
            "frametime_ms": None, "source": "Steam", "appid": appid}


def current_game():
    now = time.monotonic()
    if now - _state["at"] >= SCAN_EVERY:
        _state["at"] = now
        try:
            _state["game"] = _scan()
        except Exception:
            _state["game"] = None
    return _state["game"]
