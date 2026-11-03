"""Notifications du bureau sous Linux : l'appli observe (BecomeMonitor) les appels Notify
envoyés à org.freedesktop.Notifications sur le bus de session. Elle n'intercepte rien : la
notification s'affiche comme d'habitude, l'appli en reçoit une copie. Même interface que
notifications.WindowsNotifications (items, last_time, status, clear)."""
import html
import re
import threading
import time
from collections import deque

RULE = "type='method_call',interface='org.freedesktop.Notifications',member='Notify'"
IGNORED = {"g19 monitor", "notify-send-test"}


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

    def _on_message(self, _bus, msg):
        try:
            args = msg.get_args_list()
        except Exception:
            return
        if len(args) < 5:
            return
        app, _replaces, _icon, summary, body = (str(a) for a in args[:5])
        if not (summary or body) or app.casefold() in IGNORED:
            return
        now = time.time()
        self.items.appendleft({"app": app or "Linux", "aumid": app, "site": "",
                               "title": _plain(summary) or app, "body": _plain(body),
                               "icon": None, "time": now, "id": f"{now:.6f}"})
        self.last_time = now

    def _run(self):
        try:
            import dbus
            from dbus.mainloop.glib import DBusGMainLoop
            from gi.repository import GLib
        except ImportError as e:
            self.status = f"indisponible ({e.name})"
            return
        while True:
            try:
                loop = DBusGMainLoop()
                # bus privé : l'observateur ne peut plus rien envoyer, on ne gêne pas MPRIS
                bus = dbus.SessionBus(mainloop=loop, private=True)
                monitor = bus.get_object("org.freedesktop.DBus", "/org/freedesktop/DBus")
                monitor.BecomeMonitor([RULE], dbus.UInt32(0),
                                      dbus_interface="org.freedesktop.DBus.Monitoring")
                bus.add_message_filter(self._on_message)
                self.status = "ok"
                GLib.MainLoop().run()
            except Exception as e:
                self.status = f"erreur : {e.__class__.__name__}"
            time.sleep(10)
