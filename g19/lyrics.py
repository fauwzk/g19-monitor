"""Paroles synchronisées du morceau en cours, via LRCLIB (base libre, sans clé).

Si LRCLIB ne répond pas (coupure, erreur 5xx), secours par lyrics.ovh : paroles sans
synchronisation, et nouvel essai de LRCLIB quelques minutes plus tard pour les avoir
synchronisées."""
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
FALLBACK_RETRY = 45       # s avant de retenter LRCLIB pour un morceau lu sur le secours
BUSY_TRIES = 4            # essais quand LRCLIB répond « occupé » (503/429 : réessayer sous peu)
FAILS_BEFORE_TOAST = 2    # échecs de suite avant le bandeau (une coupure passagère : rien)
OVH = "https://api.lyrics.ovh/v1"
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
    """Réponse JSON de LRCLIB. Surchargé, il répond 503 « réessaie dans un instant » : on
    attend le Retry-After (1 s d'habitude) et on recommence, la 2e fois passe souvent."""
    url = f"{API}/{path}?{urllib.parse.urlencode(params)}"
    for attempt in range(BUSY_TRIES):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=8) as r:
                return json.loads(r.read())
        except urllib.error.HTTPError as e:
            if e.code not in (429, 502, 503, 504) or attempt == BUSY_TRIES - 1:
                raise
            try:
                wait = float(e.headers.get("Retry-After") or 0)
            except ValueError:
                wait = 0
            time.sleep(min(5.0, max(wait, 1.0) * (attempt + 1)))


def _ovh(artist, title):
    """Paroles sans synchronisation de lyrics.ovh (secours), ou None."""
    url = f"{OVH}/{urllib.parse.quote(artist)}/{urllib.parse.quote(_clean_title(title))}"
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=8) as r:
            text = (json.loads(r.read()) or {}).get("lyrics") or ""
    except Exception:
        return None
    lines = [l.strip() for l in text.replace("\r", "").splitlines()]
    while lines and not lines[0]:
        lines.pop(0)
    if not any(lines):
        return None
    return {"synced": [], "plain": lines, "instrumental": False, "fallback_at": time.time()}


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
        self._fails = 0           # échecs de suite de LRCLIB

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
            if isinstance(hit, dict) and hit.get("fallback_at") and \
                    time.time() - hit["fallback_at"] > FALLBACK_RETRY:
                # lu sur le secours : on retente LRCLIB (version synchronisée) en arrière-plan,
                # les paroles du secours restent affichées en attendant
                hit["fallback_at"] = time.time()
                threading.Thread(target=self._fetch, args=(key, media.artist, media.title,
                                                           media.album, media.duration),
                                 daemon=True).start()
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
            except urllib.error.HTTPError as e:
                if e.code != 404:     # 404 : pas cette version exacte ; le reste : panne
                    raise
            if data and not (data.get("syncedLyrics") or data.get("plainLyrics")
                             or data.get("instrumental")):
                data = None
            retry_later = False
            if not data or not (data.get("syncedLyrics") or data.get("instrumental")):
                # rien, ou seulement le texte brut : on cherche une version synchronisée
                try:
                    found = _get("search", {"artist_name": artist,
                                            "track_name": _clean_title(title)})
                except Exception:
                    if not data:
                        raise
                    found, retry_later = [], True   # recherche en panne : texte brut de « get »
                found = [f for f in found if f.get("syncedLyrics") or f.get("plainLyrics")]
                found.sort(key=lambda f: (not f.get("syncedLyrics"),
                                          abs((f.get("duration") or 0) - (duration or 0))))
                if found and (not data or found[0].get("syncedLyrics")):
                    data = found[0]
            if data:
                result = {"synced": parse_lrc(data.get("syncedLyrics")),
                          "plain": [l for l in (data.get("plainLyrics") or "").splitlines()],
                          "instrumental": bool(data.get("instrumental"))}
                if retry_later:
                    result["fallback_at"] = time.time()   # la version synchronisée plus tard
        except Exception as e:
            # LRCLIB ne répond pas : paroles du secours (non synchronisées), sinon erreur
            backup = _ovh(artist, title)
            self._failed(e, backup is not None)
            with self._lock:
                old = self._cache.get(key)
                if backup:
                    self._cache[key] = backup
                elif not (isinstance(old, dict) and old.get("fallback_at")):
                    # nouvel essai dans RETRY s, pas à chaque image
                    self._cache[key] = ("error", time.time())
            return
        self._fails, self._down = 0, False        # le service répond de nouveau
        with self._lock:
            old = self._cache.get(key)
            if result == "missing" and isinstance(old, dict) and old.get("fallback_at"):
                return            # LRCLIB n'a pas ce morceau : on garde celles du secours
            self._cache[key] = result


    def _failed(self, e, backup=False):
        """Échec de LRCLIB : bandeau au 2e échec de suite (une coupure passagère ne dit
        rien), une seule fois par panne."""
        self._fails += 1
        if self._down or self._fails < FAILS_BEFORE_TOAST:
            return
        self._down = True
        if isinstance(e, urllib.error.HTTPError):
            why = f"lrclib.net en panne (erreur {e.code})"
        elif isinstance(e, urllib.error.URLError):
            why = "pas de connexion à lrclib.net"
        else:
            why = f"lrclib.net : {e.__class__.__name__}"
        if backup:
            self.event = ("Paroles non synchronisées", why + " · secours : lyrics.ovh",
                          time.time())
        else:
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
