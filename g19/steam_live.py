"""Steam en direct : téléchargements / mises à jour en cours (manifestes locaux) et amis en
ligne (API Web Steam, avec la clé personnelle de l'utilisateur, optionnelle)."""
import json
import re
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import winreg
from pathlib import Path

import psutil

from . import config
from .steam import ci, parse_vdf, steam_root

KEY_FILE = "steam_api.json"     # {"key": "..."} — https://steamcommunity.com/dev/apikey
API = "https://api.steampowered.com"
SCAN_EVERY = 3
FRIENDS_EVERY = 30
FRIENDLIST_EVERY = 600

# EAppState de Steam (StateFlags des appmanifest_*.acf)
UPDATE_REQUIRED, FULLY_INSTALLED, RUNNING = 2, 4, 64
UPDATE_RUNNING, UPDATE_PAUSED, UPDATE_STARTED = 256, 512, 1024
VALIDATING, PREALLOCATING, DOWNLOADING, STAGING, COMMITTING = \
    131072, 524288, 1048576, 2097152, 4194304

# lignes de content_log.txt suivies, dans l'ordre : début d'une mise à jour, avec ses tailles
# (« AppID 49520 update started : download 0/14452877760, …, stage 0/16343933426 ») et
# changements d'état (« … state changed : …, (Suspended) » quand on met en pause)
EVENTS = re.compile(r"AppID (\d+) (?:update started : download (\d+)/(\d+),.*?stage (\d+)/(\d+)"
                    r"|state changed : ([^\r\n]*))")
LOG_TAIL = 512 * 1024


PERSONA = {1: "en ligne", 2: "occupé", 3: "absent", 4: "absent", 5: "en ligne", 6: "en ligne"}


def load_key():
    return ((config.load(KEY_FILE, {}) or {}).get("key") or "").strip()


def save_key(key):
    config.save(KEY_FILE, {"key": key.strip()})


def _state(flags, todo):
    if flags & (DOWNLOADING | UPDATE_RUNNING | UPDATE_STARTED):
        return "téléchargement"
    if flags & STAGING:
        return "installation"
    if flags & COMMITTING:
        return "finalisation"
    if flags & VALIDATING:
        return "vérification"
    if flags & PREALLOCATING:
        return "préparation"
    if flags & UPDATE_PAUSED:
        return "en pause"
    if flags & UPDATE_REQUIRED and todo:
        return "en attente"
    return None


def _get_json(path, **params):
    url = f"{API}{path}?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(url, headers={"User-Agent": "G19Monitor"})
    with urllib.request.urlopen(req, timeout=10) as r:
        return json.loads(r.read().decode("utf-8"))


class SteamLive:
    def __init__(self):
        self.root = steam_root()
        self.downloads = []      # [{"appid", "name", "state", "done", "total", "rate"}]
        self.friends = []        # [{"name", "state", "game", "avatar"}] en ligne seulement
        self.friends_total = 0
        self.friends_status = ""  # "" = ok, sinon raison (pas de clé, erreur…)
        self.running = False     # le client Steam tourne
        self._manifests = {}     # chemin → (mtime, AppState)
        self._progress = {}      # appid → (t, octets) pour la vitesse
        self._log = {"mtime": None, "starts": {}, "paused": {}}
        self._best = {}          # appid → octets téléchargés (jamais en arrière)
        self._live = {}          # appid → {"known": octets sûrs, "extra": écrits depuis}
        self._written = None     # octets écrits sur le disque par steam.exe, au passage d'avant
        self._friend_ids = []
        self._friend_ids_at = 0.0
        self._key = None
        self._online = None      # steamid des amis en ligne au dernier passage (None : premier)
        self.event = None        # (nom, texte, avatar, horodatage) : un ami vient de se connecter
        threading.Thread(target=self._run, daemon=True).start()

    # --- boucle ---

    def _run(self):
        last_friends = 0.0
        while True:
            try:
                self._scan()
            except Exception:
                pass
            now = time.time()
            key = load_key()
            if key != self._key:            # clé changée dans l'utilitaire : on recharge tout
                self._key, self._friend_ids_at, last_friends = key, 0.0, 0.0
            if now - last_friends >= FRIENDS_EVERY:
                last_friends = now
                self._fetch_friends()
            time.sleep(SCAN_EVERY)

    def _libraries(self):
        libs = ci(parse_vdf(_read(self.root / "steamapps" / "libraryfolders.vdf")),
                  "libraryfolders") or {}
        return {self.root} | {Path(v["path"]) for v in libs.values()
                              if isinstance(v, dict) and v.get("path")}

    def _log_events(self):
        """content_log.txt : tailles de chaque mise à jour (le manifeste ne les a pas toujours)
        et pause en cours (que les StateFlags du manifeste ne montrent pas)."""
        path = self.root / "logs" / "content_log.txt"
        try:
            st = path.stat()
        except OSError:
            return {}, {}
        if st.st_mtime != self._log["mtime"]:
            self._log["mtime"] = st.st_mtime
            try:
                with open(path, "rb") as f:
                    f.seek(max(0, st.st_size - LOG_TAIL))
                    text = f.read().decode("utf-8", errors="replace")
            except OSError:
                return self._log["starts"], self._log["paused"]
            starts, paused = {}, {}
            for m in EVENTS.finditer(text):
                appid = m.group(1)
                if m.group(2) is not None:
                    starts[appid] = tuple(int(v) for v in m.groups()[1:5])
                    paused[appid] = False
                else:
                    paused[appid] = "Suspended" in m.group(6)
            self._log["starts"], self._log["paused"] = starts, paused
        return self._log["starts"], self._log["paused"]

    def _steam_written(self):
        """Octets écrits sur le disque par steam.exe depuis son lancement (compteur Windows)."""
        pid = _reg_dword(r"Software\Valve\Steam\ActiveProcess", "pid")
        try:
            return psutil.Process(pid).io_counters().write_bytes if pid else None
        except (psutil.Error, OSError):
            return None

    def _live_done(self, appid, active, done, total, start, written):
        """Octets téléchargés en direct. Le manifeste n'est mis à jour que par à-coups (pause,
        fin…) et le dossier downloading/ est réservé d'un coup à sa taille finale : on part de
        la dernière valeur sûre (manifeste ou journal) et on ajoute ce que Steam écrit depuis sur
        le disque, ramené au volume téléchargé (le journal donne le rapport téléchargé/installé)."""
        dl0, dl_total, _st0, st_total = start or (0, 0, 0, 0)
        total = total or dl_total
        known = max(done, dl0)
        rec = self._live.get(appid)
        if not rec or known > rec["known"]:
            rec = self._live[appid] = {"known": known, "extra": 0}   # nouvelle valeur sûre
        if active and written:
            rec["extra"] += written * (dl_total / st_total if dl_total and st_total else 1)
        done = known + int(rec["extra"])
        if total:
            done = min(done, int(total * 0.999))   # 100 % : c'est Steam qui le dira
        return done, total

    def _scan(self):
        if not self.root:
            return
        starts, paused = self._log_events()
        self.running = _reg_dword(r"Software\Valve\Steam\ActiveProcess", "pid") not in (None, 0)
        w = self._steam_written()
        written = w - self._written if w is not None and self._written is not None and \
            w >= self._written else 0
        self._written = w
        credited = False         # Steam télécharge un jeu à la fois : l'écriture va au premier
        now = time.time()
        out = []
        seen = set()
        for lib in self._libraries():
            for acf in (lib / "steamapps").glob("appmanifest_*.acf"):
                seen.add(acf)
                try:
                    mtime = acf.stat().st_mtime
                except OSError:
                    continue
                hit = self._manifests.get(acf)
                if not hit or hit[0] != mtime:
                    hit = self._manifests[acf] = (mtime, ci(parse_vdf(_read(acf)), "AppState") or {})
                st = hit[1]
                appid = st.get("appid")
                flags = int(st.get("StateFlags") or 0)
                total = int(st.get("BytesToDownload") or 0)
                done = int(st.get("BytesDownloaded") or 0)
                updating = _reg_dword(rf"Software\Valve\Steam\Apps\{appid}", "Updating") == 1
                state = _state(flags, total - done) or ("téléchargement" if updating else None)
                if not state:
                    self._progress.pop(appid, None)
                    self._best.pop(appid, None)
                    self._live.pop(appid, None)
                    continue
                if state == "téléchargement" and paused.get(str(appid)):
                    state = "en pause"
                active = state == "téléchargement" and not credited
                credited = credited or active
                done, total = self._live_done(appid, active, done, total, starts.get(str(appid)),
                                              written if active else 0)
                done = self._best[appid] = max(done, self._best.get(appid, 0))
                rate = None
                prev = self._progress.get(appid)
                if prev and done > prev[1] and now > prev[0]:
                    rate = (done - prev[1]) / (now - prev[0])
                    self._progress[appid] = (now, done, rate)
                elif prev:
                    rate = prev[2] if len(prev) > 2 and now - prev[0] < 30 else None
                else:
                    self._progress[appid] = (now, done)
                out.append({"appid": appid, "name": st.get("name") or appid, "state": state,
                            "done": done, "total": total, "rate": rate})
        for acf in list(self._manifests):
            if acf not in seen:
                del self._manifests[acf]
        order = {"téléchargement": 0, "installation": 1, "finalisation": 1, "vérification": 2,
                 "préparation": 2, "en pause": 3, "en attente": 4}
        out.sort(key=lambda d: (order.get(d["state"], 9), d["name"].lower()))
        self.downloads = out

    def _steamid(self):
        users = ci(parse_vdf(_read(self.root / "config" / "loginusers.vdf")), "users") or {}
        recent = [sid for sid, v in users.items()
                  if isinstance(v, dict) and str(ci(v, "MostRecent") or "") == "1"]
        return (recent or list(users) or [None])[0]

    def _fetch_friends(self):
        if not self._key:
            self.friends, self.friends_status = [], "clé API Steam à renseigner dans l'utilitaire"
            return
        if not self.root:
            self.friends_status = "Steam introuvable"
            return
        try:
            me = self._steamid()
            if not me:
                self.friends_status = "aucun compte Steam connecté"
                return
            now = time.time()
            if now - self._friend_ids_at >= FRIENDLIST_EVERY or not self._friend_ids:
                data = _get_json("/ISteamUser/GetFriendList/v1/", key=self._key, steamid=me,
                                 relationship="friend")
                self._friend_ids = [f["steamid"] for f in
                                    (data.get("friendslist") or {}).get("friends", [])]
                self._friend_ids_at = now
            players = []
            for i in range(0, len(self._friend_ids), 100):
                data = _get_json("/ISteamUser/GetPlayerSummaries/v2/", key=self._key,
                                 steamids=",".join(self._friend_ids[i:i + 100]))
                players += (data.get("response") or {}).get("players", [])
            online = []
            for p in players:
                st = int(p.get("personastate") or 0)
                if st == 0 and not p.get("gameextrainfo"):
                    continue
                online.append({"id": p.get("steamid"), "name": p.get("personaname") or "?",
                               "state": PERSONA.get(st, "en ligne"),
                               "game": p.get("gameextrainfo") or "",
                               "avatar": p.get("avatarmedium") or ""})
            # en jeu d'abord, puis en ligne, puis absents
            rank = {"en ligne": 1, "occupé": 2, "absent": 3}
            online.sort(key=lambda f: (0 if f["game"] else rank.get(f["state"], 4),
                                       f["name"].lower()))
            # bandeau pour les amis qui viennent de se connecter (pas au premier passage)
            now_ids = {f["id"] for f in online}
            if self._online is not None:
                new = [f for f in online if f["id"] not in self._online]
                if new:
                    f = new[0]
                    text = f"joue à {f['game']}" if f["game"] else "vient de se connecter"
                    if len(new) > 1:
                        text += f" · +{len(new) - 1} ami{'s' if len(new) > 2 else ''}"
                    self.event = (f["name"], text, f["avatar"], time.time())
            self._online = now_ids
            self.friends, self.friends_total = online, len(self._friend_ids)
            self.friends_status = ""
        except urllib.error.HTTPError as e:
            self.friends_status = ("clé API refusée" if e.code in (401, 403)
                                   else f"liste d'amis privée ou indisponible ({e.code})")
        except Exception as e:
            self.friends_status = f"amis indisponibles ({e.__class__.__name__})"


def _read(path):
    try:
        return Path(path).read_text("utf-8", errors="replace")
    except OSError:
        return ""


def _reg_dword(path, name):
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, path) as k:
            return winreg.QueryValueEx(k, name)[0]
    except OSError:
        return None
