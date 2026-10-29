"""Sessions de streaming entrantes sur ce PC : Sunshine (client Moonlight) et Parsec.
Aucun des deux ne prévient les autres applis : on suit leurs journaux (seulement ce qui y est
ajouté), ce qui donne l'heure exacte de connexion / déconnexion et, pour Parsec, le nom de
l'invité. Un bandeau à chaque connexion, et le voyant de l'en-tête tant qu'une session dure."""
import os
import re
import threading
import time
from pathlib import Path

import psutil

EVERY = 1.0
SUNSHINE_LOG = Path(os.environ.get("ProgramFiles", r"C:\Program Files")) / "Sunshine" / \
    "config" / "sunshine.log"
PARSEC_LOG = Path(os.environ.get("APPDATA", "")) / "Parsec" / "log.txt"

# Sunshine : « CLIENT CONNECTED » / « CLIENT DISCONNECTED » (serveur de contrôle du flux).
# Une connexion peut écrire plusieurs lignes de début : Sunshine est suivi comme une seule
# session, ouverte ou fermée, jamais comptée.
SUN_ON = re.compile(r"CLIENT CONNECTED|New streaming session started", re.I)
SUN_OFF = re.compile(r"CLIENT DISCONNECTED|streaming session (ended|stopped)", re.I)
SUN_IP = re.compile(r"\b(\d{1,3}(?:\.\d{1,3}){3})\b")
# Parsec : « [I 2026-10-28 21:00:00] pseudo#1234567 connected. »
PARSEC = re.compile(r"\]\s+(.+?#\d+)\s+(connected|disconnected)\b", re.I)


class LogTail:
    """Lignes ajoutées à un fichier journal depuis la dernière lecture (suit les rotations)."""

    def __init__(self, path):
        self.path = path
        self.pos = None

    def read(self):
        try:
            size = self.path.stat().st_size
        except OSError:
            self.pos = None
            return None
        if self.pos is None or size < self.pos:      # premier passage, ou journal recréé
            first = self.pos is None
            self.pos = 0 if not first else max(0, size - 256 * 1024)
            if first:
                return self._chunk(size, initial=True)
        if size == self.pos:
            return []
        return self._chunk(size)

    def _chunk(self, size, initial=False):
        try:
            with open(self.path, "rb") as f:
                f.seek(self.pos)
                data = f.read(size - self.pos)
        except OSError:
            return []
        # une ligne pas encore finie sera relue au prochain passage
        cut = data.rfind(b"\n") + 1
        self.pos += cut
        lines = data[:cut].decode("utf-8", errors="replace").splitlines()
        return ("initial", lines) if initial else lines


def _running(name):
    for p in psutil.process_iter(["name"]):
        if (p.info["name"] or "").lower() == name:
            return True
    return False


class Streaming:
    def __init__(self):
        self.sessions = {}       # clé → {"app", "who", "since"}
        self.event = None        # (titre, texte, horodatage) pour le bandeau
        self._sun = LogTail(SUNSHINE_LOG)
        self._parsec = LogTail(PARSEC_LOG)
        threading.Thread(target=self._run, daemon=True).start()

    @property
    def active(self):
        return bool(self.sessions)

    def summary(self):
        """« Moonlight · Parsec (pseudo) » pour l'en-tête et l'infobulle."""
        return " · ".join(s["who"] if s["app"] == "Parsec" else "Moonlight"
                          for s in self.sessions.values())

    def _run(self):
        last_proc = 0.0
        sun_up = parsec_up = True
        while True:
            now = time.time()
            if now - last_proc > 15:
                last_proc = now
                sun_up, parsec_up = _running("sunshine.exe"), _running("parsecd.exe")
            try:
                self._sunshine(sun_up, now)
                self._parsec_log(parsec_up, now)
            except Exception:
                pass
            time.sleep(EVERY)

    def _open(self, key, app, who, now, initial):
        if key in self.sessions:
            return
        self.sessions[key] = {"app": app, "who": who, "since": now}
        if not initial:
            self.event = (who, f"connecté en streaming ({app})", now)

    def _close(self, key, now, initial):
        s = self.sessions.pop(key, None)
        if s and not initial:
            mins = max(1, int((now - s["since"]) // 60))
            self.event = (s["who"], f"déconnecté ({s['app']}) · {mins} min", now)

    def _sunshine(self, up, now):
        if not up:
            self._close("sunshine", now, False)
            return
        got = self._sun.read()
        if not got:
            return
        initial = isinstance(got, tuple)
        lines = got[1] if initial else got
        for line in lines:
            if SUN_ON.search(line):
                ip = SUN_IP.search(line.split("]:", 1)[-1])
                who = f"Moonlight {ip.group(1)}" if ip else "Moonlight"
                self._open("sunshine", "Sunshine", who, now, initial)
            elif SUN_OFF.search(line):
                self._close("sunshine", now, initial)

    def _parsec_log(self, up, now):
        if not up:
            for key in [k for k in self.sessions if k.startswith("parsec:")]:
                self._close(key, now, False)
            return
        got = self._parsec.read()
        if not got:
            return
        initial = isinstance(got, tuple)
        for line in (got[1] if initial else got):
            m = PARSEC.search(line)
            if not m:
                continue
            who = m.group(1).strip()
            key = "parsec:" + who
            if m.group(2).lower() == "connected":
                self._open(key, "Parsec", who, now, initial)
            else:
                self._close(key, now, initial)
