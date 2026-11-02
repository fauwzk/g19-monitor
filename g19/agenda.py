"""Agenda Google (ou tout agenda iCal) : prochains événements et rappel avant chacun.

Pas de compte à connecter : l'« adresse secrète au format iCal » de l'agenda (Google Agenda →
Paramètres de l'agenda → Intégrer l'agenda), gardée dans calendar.json avec les autres accès
(%LOCALAPPDATA%\\G19Monitor, jamais dans le dépôt). Plusieurs agendas possibles.
Événements récurrents, exceptions et fuseaux horaires : icalendar + recurring-ical-events."""
import re
import threading
import time
import urllib.error
import urllib.request
from datetime import date, datetime, timedelta

from . import config

CAL_FILE = "calendar.json"        # {"urls": ["https://calendar.google.com/…/basic.ics"]}
REFRESH = 10 * 60                 # s entre deux lectures
DAYS = 7                          # événements gardés : de maintenant à J+7
UA = {"User-Agent": "G19Monitor (Logitech G19 LCD applet)"}
LINK = re.compile(r"https://(?:meet\.google\.com|[\w.-]*zoom\.us|teams\.microsoft\.com|"
                  r"teams\.live\.com)/[^\s<>\"']+")


def load_urls():
    data = config.load(CAL_FILE, {}) or {}
    return [u.strip() for u in data.get("urls") or [] if u and u.strip()]


def save_urls(urls):
    config.save(CAL_FILE, {"urls": [u.strip() for u in urls if u.strip()]})


def _epoch(v):
    """dtstart / dtend iCal → (horodatage, toute la journée ?)."""
    if isinstance(v, datetime):
        return (v.timestamp() if v.tzinfo else time.mktime(v.timetuple())), False
    if isinstance(v, date):
        return time.mktime(datetime(v.year, v.month, v.day).timetuple()), True
    return None, False


def parse(ics, now, days=DAYS):
    """Texte iCal → événements de maintenant (en cours compris) à `days` jours, triés."""
    import icalendar
    import recurring_ical_events

    cal = icalendar.Calendar.from_ical(ics)
    name = str(cal.get("X-WR-CALNAME") or "")
    start = datetime.fromtimestamp(now) - timedelta(days=1)
    end = datetime.fromtimestamp(now) + timedelta(days=days)
    out = []
    for ev in recurring_ical_events.of(cal).between(start, end):
        s, all_day = _epoch(ev.decoded("DTSTART"))
        if s is None:
            continue
        try:
            e, _ = _epoch(ev.decoded("DTEND"))
        except KeyError:
            e = None
        e = e or (s + (86400 if all_day else 3600))
        if e <= now:
            continue
        text = " ".join(str(ev.get(k) or "") for k in ("LOCATION", "DESCRIPTION",
                                                        "X-GOOGLE-CONFERENCE"))
        link = LINK.search(text)
        out.append({"uid": str(ev.get("UID") or ""), "title": str(ev.get("SUMMARY") or
                                                                  "(sans titre)"),
                    "start": s, "end": e, "all_day": all_day,
                    "location": str(ev.get("LOCATION") or "").split("\n")[0],
                    "calendar": name, "url": link.group(0) if link else None})
    out.sort(key=lambda x: (x["start"], not x["all_day"]))
    return out


class Agenda:
    def __init__(self, remind_minutes=lambda: 10):
        self.remind_minutes = remind_minutes
        self.events = []
        self.status = "lecture…"        # "" : à jour ; "non configuré" ; erreur
        self.updated_at = 0.0
        self.event = None               # (titre, texte, horodatage, lien) : rappel
        self._reminded = set()
        self._wake = threading.Event()
        threading.Thread(target=self._run, daemon=True, name="agenda").start()

    def configured(self):
        return bool(load_urls())

    def check_now(self):
        self._wake.set()

    def _fetch(self, urls, now):
        events, errors = [], []
        for url in urls:
            try:
                req = urllib.request.Request(url.replace("webcal://", "https://"), headers=UA)
                with urllib.request.urlopen(req, timeout=20) as r:
                    events += parse(r.read(), now)
            except urllib.error.HTTPError as e:
                errors.append("lien refusé (404 : adresse secrète réinitialisée ?)"
                              if e.code == 404 else f"erreur {e.code}")
            except Exception as e:
                errors.append(str(e) or e.__class__.__name__)
        events.sort(key=lambda x: (x["start"], not x["all_day"]))
        return events, errors

    def _remind(self, now):
        ahead = max(0, int(self.remind_minutes() or 0)) * 60
        if not ahead:
            return
        for ev in self.events:
            key = (ev["uid"], ev["start"])
            if ev["all_day"] or key in self._reminded or ev["start"] < now:
                continue
            if ev["start"] - now <= ahead:
                self._reminded.add(key)
                mins = max(1, round((ev["start"] - now) / 60))
                when = time.strftime("%H:%M", time.localtime(ev["start"]))
                body = f"dans {mins} min · {when}" + (f" · {ev['location']}"
                                                       if ev["location"] else "")
                self.event = (ev["title"], body, now, ev["url"])

    def _run(self):
        last = 0.0
        while True:
            now = time.time()
            urls = load_urls()
            if not urls:
                self.events, self.status = [], "non configuré"
            elif now - last >= REFRESH or self._wake.is_set():
                self._wake.clear()
                last = now
                events, errors = self._fetch(urls, now)
                if events or not errors:
                    self.events, self.updated_at = events, now
                self.status = errors[0] if errors and not events else ""
            # les événements passés quittent la liste sans attendre la relecture
            self.events = [e for e in self.events if e["end"] > now]
            self._remind(now)
            self._wake.wait(15)


def day_label(ts, now):
    """« Aujourd'hui », « Demain », sinon « mer. 4 nov. »."""
    from .render import JOURS, MOIS
    d0 = datetime.fromtimestamp(now).date()
    d = datetime.fromtimestamp(ts).date()
    if d == d0:
        return "Aujourd'hui"
    if d == d0 + timedelta(days=1):
        return "Demain"
    return f"{JOURS[d.weekday()]} {d.day} {MOIS[d.month - 1]}"
