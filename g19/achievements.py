"""Succès Steam débloqués pendant la partie : bandeau sur le G19 et liste dans le récapitulatif.

API Web Steam avec la clé de l'utilisateur (steam_api.json) : la liste des succès du jeu (noms et
icônes en français) une fois par jeu, puis ceux du joueur toutes les POLL secondes tant que le
jeu tourne. Il faut que les « détails des jeux » du profil Steam soient publics."""
import io
import json
import threading
import time
import urllib.error
import urllib.parse
import urllib.request

from PIL import Image, ImageDraw

from .steam_live import load_key

API = "https://api.steampowered.com"
POLL = 30            # s entre deux lectures pendant la partie
ICON = 26            # côté de l'icône dans le bandeau


def _get_json(path, **params):
    url = f"{API}{path}?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(url, headers={"User-Agent": "G19Monitor"})
    with urllib.request.urlopen(req, timeout=10) as r:
        return json.loads(r.read().decode("utf-8"))


def _icon(url):
    """Icône du succès en carré arrondi (RGBA), ou None."""
    if not url:
        return None
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "G19Monitor"})
        with urllib.request.urlopen(req, timeout=10) as r:
            im = Image.open(io.BytesIO(r.read())).convert("RGB").resize((ICON, ICON), Image.LANCZOS)
    except Exception:
        return None
    mask = Image.new("L", (ICON, ICON), 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, ICON - 1, ICON - 1), 5, fill=255)
    im.putalpha(mask)
    return im


def unlocked_since(player, known):
    """Succès débloqués absents de `known` : [(apiname, unlocktime)], du plus ancien au plus récent."""
    new = [(a["apiname"], a.get("unlocktime") or 0) for a in player
           if a.get("achieved") and a["apiname"] not in known]
    return sorted(new, key=lambda x: x[1])


class Achievements:
    def __init__(self, get_steamid):
        self.get_steamid = get_steamid   # steamid64 du compte Steam du PC (loginusers.vdf)
        self.event = None        # (titre, texte, icône, horodatage) : succès qui vient de tomber
        self.unlocked = []       # [{"name", "desc", "rarity", "at"}] de la partie en cours
        self.status = ""
        self._appid = None
        self._wake = threading.Event()
        threading.Thread(target=self._run, daemon=True, name="succès Steam").start()

    def watch(self, appid):
        """Jeu Steam en cours (appid) ou None ; appelé chaque seconde par la boucle."""
        appid = str(appid) if appid else None
        if appid != self._appid:
            self._appid = appid
            self.unlocked = []
            self._wake.set()

    def _run(self):
        schema, rarity, known, current = None, {}, None, None   # schema None : pas encore lu
        while True:
            appid, key = self._appid, load_key()
            if appid != current:          # autre jeu (ou fin de partie) : on repart de zéro
                current, schema, rarity, known = appid, None, {}, None
            if appid and key:
                try:
                    steamid = self.get_steamid()
                    if schema is None:
                        schema = self._schema(key, appid)     # {} : jeu sans succès
                        rarity = self._rarity(appid) if schema else {}
                    if schema and steamid:
                        data = _get_json("/ISteamUserStats/GetPlayerAchievements/v1/", key=key,
                                         steamid=steamid, appid=appid, l="french")
                        player = (data.get("playerstats") or {}).get("achievements") or []
                        if known is None:      # première lecture : ce qui était déjà acquis
                            known = {a["apiname"] for a in player if a.get("achieved")}
                        else:
                            for name, _when in unlocked_since(player, known):
                                known.add(name)
                                self._announce(schema.get(name) or {"name": name},
                                               rarity.get(name), appid)
                        self.status = ""
                except urllib.error.HTTPError as e:
                    self.status = ("profil Steam privé (détails des jeux)" if e.code in (400, 403)
                                   else f"API Steam : erreur {e.code}")
                except Exception as e:
                    self.status = str(e) or e.__class__.__name__
            if self._wake.wait(POLL):
                self._wake.clear()

    @staticmethod
    def _schema(key, appid):
        try:
            data = _get_json("/ISteamUserStats/GetSchemaForGame/v2/", key=key, appid=appid,
                             l="french")
        except urllib.error.HTTPError as e:
            if e.code == 400:      # jeu sans statistiques ni succès
                return {}
            raise
        items = (((data.get("game") or {}).get("availableGameStats") or {})
                 .get("achievements") or [])
        return {a["name"]: {"name": a.get("displayName") or a["name"],
                            "desc": a.get("description") or "", "icon": a.get("icon")}
                for a in items}

    @staticmethod
    def _rarity(appid):
        try:
            data = _get_json("/ISteamUserStats/GetGlobalAchievementPercentagesForApp/v2/",
                             gameid=appid)
        except Exception:
            return {}
        items = (data.get("achievementpercentages") or {}).get("achievements") or []
        return {a["name"]: float(a.get("percent") or 0) for a in items}

    def _announce(self, info, rarity, appid):
        if appid != self._appid:
            return
        now = time.time()
        body = info.get("desc") or "succès débloqué"
        if rarity is not None:     # la rareté d'abord : la description peut être coupée
            body = f"{rarity:.1f} % des joueurs · ".replace(".", ",") + body
        self.unlocked.append({"name": info["name"], "desc": info.get("desc") or "",
                              "rarity": rarity, "at": now})
        self.event = (f"🏆 {info['name']}", body, _icon(info.get("icon")), now)
