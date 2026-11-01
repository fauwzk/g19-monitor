"""Paroles synchronisées du morceau en cours, via LRCLIB (base libre, sans clé)."""
import json
import re
import threading
import time
import urllib.error
import urllib.parse
import urllib.request

API = "https://lrclib.net/api"
UA = {"User-Agent": "G19Monitor (Logitech G19 LCD applet)"}
RETRY = 60                # s avant de retenter un morceau après une erreur (service en panne…)
LRC_LINE = re.compile(r"\[(\d+):(\d+(?:\.\d+)?)\]")


def parse_lrc(text):
    """[(secondes, ligne)] triés, à partir d'un texte LRC."""
    out = []
    for raw in (text or "").splitlines():
        stamps = LRC_LINE.findall(raw)
        line = LRC_LINE.sub("", raw).strip()
        for m, s in stamps:
            out.append((int(m) * 60 + float(s), line))
    return sorted(out)


def _get(path, params):
    url = f"{API}/{path}?{urllib.parse.urlencode(params)}"
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=8) as r:
        return json.loads(r.read())


def _clean_title(title):
    # « Titre - Remastered 2011 », « Titre (feat. X) » : LRCLIB indexe le titre principal
    return re.sub(r"\s*[-–(\[].*?(remaster|feat\.|ft\.|version|edit|live).*$", "", title,
                  flags=re.I).strip() or title


class Lyrics:
    def __init__(self):
        self._cache = {}          # (artiste, titre) → résultat (ou "loading")
        self._lock = threading.Lock()
        self.event = None         # (titre, texte, horodatage) : le service ne répond plus
        self._down = False        # panne déjà signalée (un seul bandeau par panne)

    def get(self, media):
        """{'synced': [(t, ligne)], 'plain': [lignes], 'instrumental': bool} ; None pendant la
        recherche ou si rien n'est trouvé ('missing' dans ce cas)."""
        if not media or not media.title:
            return None
        key = (media.artist.lower(), media.title.lower())
        with self._lock:
            hit = self._cache.get(key)
            if isinstance(hit, tuple):        # ("error", heure) : on attend avant de retenter
                if time.time() - hit[1] < RETRY:
                    return "loading"
                hit = None
            if hit is None:
                self._cache[key] = "loading"
                threading.Thread(target=self._fetch, args=(key, media.artist, media.title,
                                                           media.album, media.duration),
                                 daemon=True).start()
                return "loading"
        return hit

    def _fetch(self, key, artist, title, album, duration):
        result = "missing"
        try:
            data = None
            params = {"artist_name": artist, "track_name": _clean_title(title)}
            if album:
                params["album_name"] = album
            if duration:
                params["duration"] = round(duration)
            try:
                data = _get("get", params)
            except urllib.error.HTTPError:
                data = None
            if not data or not (data.get("syncedLyrics") or data.get("plainLyrics")
                                or data.get("instrumental")):
                found = _get("search", {"artist_name": artist, "track_name": _clean_title(title)})
                found = [f for f in found if f.get("syncedLyrics") or f.get("plainLyrics")]
                if duration:
                    found.sort(key=lambda f: (not f.get("syncedLyrics"),
                                              abs((f.get("duration") or 0) - duration)))
                data = found[0] if found else None
            if data:
                result = {"synced": parse_lrc(data.get("syncedLyrics")),
                          "plain": [l for l in (data.get("plainLyrics") or "").splitlines()],
                          "instrumental": bool(data.get("instrumental"))}
        except Exception as e:
            result = "error"          # réseau ou service en panne : on retentera plus tard
            self._failed(e)
        if result != "error":
            self._down = False        # le service répond de nouveau
        with self._lock:
            # erreur réseau ou service en panne : nouvel essai dans RETRY s, pas à chaque image
            self._cache[key] = ("error", time.time()) if result == "error" else result


    def _failed(self, e):
        """Premier échec d'une panne : bandeau sur le G19 (pas un par morceau)."""
        if self._down:
            return
        self._down = True
        if isinstance(e, urllib.error.HTTPError):
            why = f"lrclib.net en panne (erreur {e.code})"
        elif isinstance(e, urllib.error.URLError):
            why = "pas de connexion à lrclib.net"
        else:
            why = f"lrclib.net : {e.__class__.__name__}"
        self.event = ("Paroles indisponibles", why, time.time())   # nouvel essai chaque minute


def current_index(synced, pos):
    """Indice de la ligne en cours à la position `pos` (s), -1 avant la première."""
    lo, hi = 0, len(synced)
    while lo < hi:
        mid = (lo + hi) // 2
        if synced[mid][0] <= pos:
            lo = mid + 1
        else:
            hi = mid
    return lo - 1
