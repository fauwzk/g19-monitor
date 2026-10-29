"""Suivi des sessions de jeu : jeu détecté par RTSS (tous launchers), infos Steam si dispo,
historique local."""
import re
import threading
import time
import urllib.request
from datetime import datetime
from pathlib import Path

from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageOps, ImageStat

from . import config
from .catalog import GameCatalog
from .covers import exe_icon, store_appid
from .lcd import W, H

HISTORY_FILE = "games.json"
HISTORY_MAX = 300
MIN_SESSION = 60      # s : en dessous, la session n'est pas gardée
GRACE = 90            # s sans images avant de considérer le jeu fermé (alt-tab, chargement…)
COVER = (84, 126)
THUMB = (30, 45)
CDN = "https://shared.cloudflare.steamstatic.com/store_item_assets/steam/apps/{}/{}.jpg"

KNOWN = {"valorant-win64-shipping": "VALORANT", "league of legends": "League of Legends",
         "r5apex": "Apex Legends", "cs2": "Counter-Strike 2", "fortniteclient-win64-shipping":
         "Fortnite", "rocketleague": "Rocket League", "overwatch": "Overwatch 2",
         "gta5": "Grand Theft Auto V", "eldenring": "ELDEN RING", "minecraft": "Minecraft",
         "rainbowsix": "Rainbow Six Siege", "rainbowsix_be": "Rainbow Six Siege"}


def pretty_exe(name):
    stem = re.sub(r"\.exe$", "", name, flags=re.I)
    if stem.lower() in KNOWN:
        return KNOWN[stem.lower()]
    stem = re.sub(r"[-_](Win64|Win32|x64)?[-_]?Shipping$|[-_](Win64|x64|DX1[12])$", "", stem, flags=re.I)
    return re.sub(r"(?<=[a-z])(?=[A-Z])|_", " ", stem).strip()


def rounded(img, radius):
    mask = Image.new("L", img.size, 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, img.width - 1, img.height - 1), radius, fill=255)
    img = img.convert("RGB")
    img.putalpha(mask)
    return img


def icon_card(icon, size, radius):
    """Fausse pochette : dégradé dans la couleur de l'icône, icône au centre."""
    r, g, b = (int(v) for v in ImageStat.Stat(icon.convert("RGB"), icon.getchannel("A")).mean[:3])
    card = Image.new("RGB", size)
    d = ImageDraw.Draw(card)
    for y in range(size[1]):
        f = 0.55 - 0.4 * y / size[1]
        d.line((0, y, size[0], y), fill=(int(r * f), int(g * f), int(b * f)))
    side = int(min(size) * 0.72)
    ic = ImageOps.contain(icon, (side, side), Image.LANCZOS)
    card.paste(ic, ((size[0] - ic.width) // 2, int(size[1] * 0.42 - ic.height / 2)), ic)
    return rounded(card, radius)


def _curve(values, n):
    """Courbe réduite à n points (moyennes), pour le récapitulatif de fin de partie."""
    vals = list(values)
    if len(vals) <= n:
        return [round(v) for v in vals]
    step = len(vals) / n
    return [round(sum(vals[int(i * step):int((i + 1) * step)] or [vals[int(i * step)]])
                  / max(1, len(vals[int(i * step):int((i + 1) * step)]))) for i in range(n)]


class Session:
    def __init__(self, game, ident, now):
        self.exe = game["path"]
        self.appid = ident.get("steam_appid")
        self.launcher = ident.get("launcher")
        self.name = ident.get("name") or pretty_exe(game["name"])
        self.start = now
        self.last_seen = now
        self.fps = []           # un échantillon par seconde
        self.temp_max = 0.0
        self.cpu_temp_max = 0.0
        self.power_sum = 0.0
        self.power_n = 0

    @property
    def duration(self):
        return self.last_seen - self.start

    def stats(self):
        if not self.fps:
            return None
        vals = sorted(self.fps)
        low = vals[: max(1, len(vals) // 100)]
        return {"avg": sum(vals) / len(vals), "low1": sum(low) / len(low),
                "max": vals[-1], "min": vals[0]}

    def to_record(self):
        s = self.stats() or {}
        return {"name": self.name, "appid": self.appid, "launcher": self.launcher, "exe": self.exe,
                "start": self.start, "duration": self.duration,
                "fps_avg": s.get("avg"), "fps_low1": s.get("low1"),
                "temp_max": self.temp_max or None,
                "cpu_temp_max": self.cpu_temp_max or None, "fps_max": s.get("max"),
                "fps_curve": _curve(self.fps, 60),
                "power_avg": self.power_sum / self.power_n if self.power_n else None}


class GameTracker:
    def __init__(self):
        self.history = config.load(HISTORY_FILE, [])
        self.session = None
        self.ended = None       # (enregistrement, horodatage) : partie qui vient de finir
        self.catalog = GameCatalog()
        self._images = {}       # (exe, type) → image PIL prête à coller
        self._pending = set()
        self._lock = threading.Lock()

    @property
    def steam(self):
        return self.catalog.steam

    # --- sessions ---

    def update(self, game, sensors, now):
        """Toutes les secondes, avec le jeu RTSS courant (ou None) et les capteurs GPU."""
        s = self.session
        if game and s and game["path"] == s.exe:
            s.last_seen = now
            s.fps.append(game["fps"])
            s.temp_max = max(s.temp_max, sensors.get("hotspot", sensors.get("temp", 0.0)))
            s.cpu_temp_max = max(s.cpu_temp_max, sensors.get("cpu_temp") or 0.0)
            if sensors.get("power"):
                s.power_sum += sensors["power"]
                s.power_n += 1
        elif game:
            self._end()
            self.session = Session(game, self.catalog.identify(game["path"], game["name"]), now)
            last = self.history[0] if self.history else None
            if last and last["exe"] == game["path"] and now - (last["start"] + last["duration"]) < GRACE:
                # même jeu juste après une relance de l'appli : on reprend la session
                self.history.pop(0)
                self.session.start = last["start"]
                self.session.temp_max = last.get("temp_max") or 0.0
        elif s and now - s.last_seen > GRACE:
            self._end()

    def _end(self):
        s, self.session = self.session, None
        if s and s.duration >= MIN_SESSION:
            self.history.insert(0, s.to_record())
            self.ended = (self.history[0], time.time())
            del self.history[HISTORY_MAX:]
            config.save(HISTORY_FILE, self.history)

    def close(self):
        self._end()

    def today_seconds(self, now):
        midnight = datetime.fromtimestamp(now).replace(hour=0, minute=0, second=0).timestamp()
        total = sum(min(r["duration"], r["start"] + r["duration"] - midnight)
                    for r in self.history if r["start"] + r["duration"] > midnight)
        if self.session:
            total += self.session.last_seen - max(self.session.start, midnight)
        return max(total, 0)

    def total_seconds(self, item):
        """(secondes, source) : temps Steam si connu, sinon le temps suivi par l'appli."""
        appid, exe = self._get(item, "appid"), self._get(item, "exe")
        if self.steam and appid:
            pt = self.steam.playtime(appid)
            if pt:
                extra = self.session.duration if self.session and self.session.exe == exe else 0
                return pt[0] * 60 + extra, "Steam"
        tracked = sum(r["duration"] for r in self.history if r.get("exe") == exe)
        if self.session and self.session.exe == exe:
            tracked += self.session.duration
        return tracked, "suivi"

    def recent(self, n=4):
        """Derniers jeux distincts joués."""
        seen, out = set(), []
        for r in self.history:
            key = r.get("exe") or r["name"]
            if key not in seen:
                seen.add(key)
                out.append(r)
            if len(out) == n:
                break
        return out

    # --- images (chargées en tâche de fond) ---

    @staticmethod
    def _get(item, key):
        return item.get(key) if isinstance(item, dict) else getattr(item, key, None)

    def image(self, item, kind):
        """Visuel d'une session ou d'un enregistrement d'historique ; kind : 'cover', 'thumb'
        ou 'bg'. None tant que l'image n'est pas prête."""
        exe = self._get(item, "exe")
        if not exe:
            return None
        key = (exe, kind)
        with self._lock:
            if key in self._images:
                return self._images[key]
            if exe in self._pending:
                return None
            self._pending.add(exe)
        info = {k: self._get(item, k) for k in ("exe", "appid", "name")}
        threading.Thread(target=self._load_images, args=(info,), daemon=True).start()
        return None

    def _steam_image(self, appid, kind):
        path = self.steam.image(appid, kind) if self.steam else None
        if path:
            return Image.open(path)
        cache = config.DATA_DIR / "covers" / f"{appid}_{kind}.jpg"
        if not cache.exists():
            try:
                with urllib.request.urlopen(CDN.format(appid, kind), timeout=5) as r:
                    data = r.read()
            except Exception:
                return None
            cache.parent.mkdir(parents=True, exist_ok=True)
            cache.write_bytes(data)
        return Image.open(cache)

    def _load_images(self, info):
        result = {}
        try:
            appid = info["appid"] or store_appid(info["name"])
            cover = hero = None
            if appid:
                cover = self._steam_image(appid, "library_600x900")
                hero = self._steam_image(appid, "library_hero_blur") or \
                    self._steam_image(appid, "library_hero")
            if cover:
                result["cover"] = rounded(ImageOps.fit(cover.convert("RGB"), COVER, Image.LANCZOS), 6)
                result["thumb"] = rounded(ImageOps.fit(cover.convert("RGB"), THUMB, Image.LANCZOS), 3)
            icon = None
            if not cover and Path(info["exe"]).exists():
                icon = exe_icon(info["exe"])
                if icon:
                    result["cover"] = icon_card(icon, COVER, 6)
                    result["thumb"] = icon_card(icon, THUMB, 3)
            source = hero or icon or cover
            if source:
                bg = ImageOps.fit(source.convert("RGB"), (W, H), Image.LANCZOS)
                blur = 6 if hero else 30
                result["bg"] = ImageEnhance.Brightness(bg.filter(ImageFilter.GaussianBlur(blur))) \
                    .enhance(0.3 if hero else 0.45)
        except Exception:
            pass
        with self._lock:
            for kind in ("cover", "thumb", "bg"):
                self._images[(info["exe"], kind)] = result.get(kind)
            self._pending.discard(info["exe"])
