"""Bilan du jour : temps passé sur le PC, en jeu, à écouter de la musique, heure par heure.

Compté par l'appli pendant qu'elle tourne (une seconde à la fois), gardé 14 jours dans
day_log.json. Le soir, à l'heure réglée, un bandeau résume la journée."""
import time

from . import config

FILE = "day_log.json"
KEEP_DAYS = 14
SAVE_EVERY = 60          # s entre deux enregistrements
MAX_STEP = 5             # s comptées au plus entre deux appels (veille, appli figée)
MIN_TRACK = 30           # s d'écoute pour qu'un morceau compte
MIN_PC = 600             # pas de bandeau du soir pour une journée de moins de 10 min


def day_key(t):
    return time.strftime("%Y-%m-%d", time.localtime(t))


def empty_day():
    return {"pc": 0.0, "game": 0.0, "music": 0.0, "tracks": 0,
            "hours_pc": [0.0] * 24, "hours_game": [0.0] * 24, "hours_music": [0.0] * 24,
            "games": {}, "artists": {}, "first": None, "last": None}


def summary(day):
    """« PC 6 h 12 · jeu 1 h 40 · 23 morceaux »."""
    from .render import fmt_duration
    parts = [f"PC {fmt_duration(day['pc'])}"]
    if day["game"] >= 60:
        parts.append(f"jeu {fmt_duration(day['game'])}")
    if day["tracks"]:
        parts.append(f"{day['tracks']} morceau{'x' if day['tracks'] > 1 else ''}")
    return " · ".join(parts)


class DayLog:
    def __init__(self):
        data = config.load(FILE, {})
        self.days = data if isinstance(data, dict) else {}
        for k, v in list(self.days.items()):
            if not isinstance(v, dict):
                del self.days[k]
            else:
                self.days[k] = {**empty_day(), **v}
        self.event = None        # (titre, texte, horodatage) : bilan du soir
        self._last = None
        self._saved = None       # dernier enregistrement (horloge des appels à tick)
        self._track = None       # (titre, artiste) en cours d'écoute
        self._heard = 0.0        # … écouté depuis s
        self._counted = False

    def day(self, t, offset=0):
        """Journée de `t` (offset -1 : la veille), vide si rien n'a été compté."""
        return self.days.get(day_key(t + offset * 86400)) or empty_day()

    def tick(self, now, active, game, media, recap_hour=21):
        """Toutes les secondes. `active` : quelqu'un est devant le PC (pas au repos) ;
        `game` : nom du jeu en cours ou None ; `media` : media.MediaState ou None."""
        dt = 0.0 if self._last is None else max(0.0, min(MAX_STEP, now - self._last))
        self._last = now
        key = day_key(now)
        day = self.days.get(key)
        if day is None:
            day = self.days[key] = empty_day()
        hour = time.localtime(now).tm_hour
        if active or game:
            day["pc"] += dt
            day["hours_pc"][hour] += dt
            day["first"] = day["first"] or now
            day["last"] = now
        if game:
            day["game"] += dt
            day["hours_game"][hour] += dt
            day["games"][game] = day["games"].get(game, 0.0) + dt
        if media and media.title and media.playing:
            track = (media.title, media.artist or "")
            if track != self._track:
                self._track, self._heard, self._counted = track, 0.0, False
            self._heard += dt
            day["music"] += dt
            day["hours_music"][hour] += dt
            if not self._counted and self._heard >= MIN_TRACK:
                self._counted = True
                day["tracks"] += 1
                if media.artist:
                    day["artists"][media.artist] = day["artists"].get(media.artist, 0) + 1
        if recap_hour and hour >= recap_hour and not day.get("recap_shown") \
                and day["pc"] >= MIN_PC:
            day["recap_shown"] = True
            self.event = ("Bilan du jour", summary(day), now)
        if self._saved is None:
            self._saved = now
        elif now - self._saved >= SAVE_EVERY:
            self.save(now)

    def save(self, now=None):
        now = now or time.time()
        self._saved = now
        keep = {day_key(now - k * 86400) for k in range(KEEP_DAYS)}
        self.days = {k: v for k, v in self.days.items() if k in keep}
        config.save(FILE, self.days)
