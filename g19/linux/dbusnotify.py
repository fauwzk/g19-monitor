"""Notifications du bureau sous Linux : `busctl monitor` observe les appels Notify envoyés à
org.freedesktop.Notifications sur le bus de session (un message JSON par ligne). L'appli
n'intercepte rien : la notification s'affiche comme d'habitude, elle en reçoit une copie.
Processus à part, pas de boucle GLib (celle de l'icône de la barre des tâches suffit).
Même interface que notifications.WindowsNotifications (items, last_time, status, clear)."""
import html
import json
import re
import subprocess
import threading
import time
from collections import deque

from .pulse import _die_with_parent

MATCH = "type=method_call,interface=org.freedesktop.Notifications,member=Notify"
IGNORED = {"g19 monitor"}


def _plain(text):
    """Texte brut d'une notification (KDE et GNOME acceptent un peu de HTML)."""
    return " ".join(html.unescape(re.sub(r"<[^>]+>", "", str(text or ""))).split())


class LinuxNotifications:
    def __init__(self):
        self.items = deque(maxlen=30)
        self.status = "init"
        self.last_time = 0.0
        threading.Thread(target=self._run, daemon=True, name="notifications").start()

    def clear(self):
        self.items.clear()

    def _add(self, args):
        if len(args) < 5:
            return
        app, _replaces, _icon, summary, body = (args[0], args[1], args[2], args[3], args[4])
        app = str(app or "")
        if not (summary or body) or app.casefold() in IGNORED:
            return
        now = time.time()
        self.items.appendleft({"app": app or "Linux", "aumid": app, "site": "",
                               "title": _plain(summary) or app, "body": _plain(body),
                               "icon": None, "time": now, "id": f"{now:.6f}"})
        self.last_time = now

    def _run(self):
        while True:
            try:
                p = subprocess.Popen(["busctl", "--user", "monitor", "--json=short",
                                      "--match", MATCH], stdout=subprocess.PIPE,
                                     stdin=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                     text=True, preexec_fn=_die_with_parent)
                self.status = "ok"
                for line in p.stdout:
                    try:
                        msg = json.loads(line)
                    except ValueError:
                        continue
                    if msg.get("member") == "Notify":
                        self._add((msg.get("payload") or {}).get("data") or [])
                self.status = "busctl s'est arrêté"
            except OSError as e:
                self.status = f"indisponible ({e.__class__.__name__})"
            time.sleep(10)
