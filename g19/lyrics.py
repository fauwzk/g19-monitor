"""Paroles synchronisées du morceau en cours, via LRCLIB (base libre, sans clé)."""
import json
import re
import threading
import urllib.error
import urllib.parse
import urllib.request

API = "https://lrclib.net/api"
UA = {"User-Agent": "G19Monitor (Logitech G19 LCD applet)"}
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

    def get(self, media):
        """{'synced': [(t, ligne)], 'plain': [lignes], 'instrumental': bool} ; None pendant la
        recherche ou si rien n'est trouvé ('missing' dans ce cas)."""
        if not media or not media.title:
            return None
        key = (media.artist.lower(), media.title.lower())
        with self._lock:
            hit = self._cache.get(key)
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
        except Exception:
            result = "error"          # réseau : on retentera au prochain morceau
        with self._lock:
            if result == "error":
                self._cache.pop(key, None)
            else:
                self._cache[key] = result


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
