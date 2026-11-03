"""« Ne pas déranger » sous Linux (KDE Plasma, et tout serveur de notifications qui expose
Inhibited / Inhibit / UnInhibit) : même interface que dnd.DoNotDisturb (supported, active,
event, toggle). Activé depuis le G19 : l'appli tient une inhibition, relâchée au second appui
(ou quand elle s'arrête). Activé depuis Plasma : l'appli le voit (Inhibited, ou « jusqu'à »
dans plasmanotifyrc) ; on le désactive alors depuis Plasma."""
import threading
import time
from datetime import datetime
from pathlib import Path

POLL = 1
PLASMA_RC = Path.home() / ".config" / "plasmanotifyrc"


def _plasma_until():
    """Ne pas déranger de Plasma réglé « jusqu'à » une heure encore à venir ?"""
    try:
        text = PLASMA_RC.read_text("utf-8", "replace")
    except OSError:
        return False
    section = ""
    for line in text.splitlines():
        if line.startswith("["):
            section = line.strip()
        elif section == "[DoNotDisturb]" and line.startswith("Until="):
            value = line[6:].strip()
            for fmt in ("%Y,%m,%d,%H,%M,%S", "%Y-%m-%dT%H:%M:%S"):
                try:
                    return datetime.strptime(value[:19], fmt) > datetime.now()
                except ValueError:
                    continue
    return False


class LinuxDnd:
    def __init__(self):
        self.supported = False
        self.active = False
        self.event = None
        self._cookie = None
        self._want = None
        self._wake = threading.Event()
        threading.Thread(target=self._run, daemon=True, name="ne pas déranger").start()

    def toggle(self):
        self._want = not self.active
        self._wake.set()

    def _run(self):
        try:
            import dbus
            bus = dbus.SessionBus()
            obj = bus.get_object("org.freedesktop.Notifications", "/org/freedesktop/Notifications")
            notif = dbus.Interface(obj, "org.freedesktop.Notifications")
            props = dbus.Interface(obj, "org.freedesktop.DBus.Properties")
            props.Get("org.freedesktop.Notifications", "Inhibited")
            self.supported = True
        except Exception:
            return
        while True:
            try:
                if self._want is not None:
                    want, self._want = self._want, None
                    if want and self._cookie is None:
                        self._cookie = int(notif.Inhibit("g19-monitor", "Ne pas déranger (G19)",
                                                         {}))
                    elif not want and self._cookie is not None:
                        notif.UnInhibit(dbus.UInt32(self._cookie))
                        self._cookie = None
                    time.sleep(0.3)
                    self.active = self._read(props)
                    if not want and self.active:
                        text = "activé depuis Plasma : à couper là-bas"
                    else:
                        text = "notifications en pause" if self.active else \
                            "les notifications reprennent"
                    self.event = ("Ne pas déranger " + ("activé" if self.active else "désactivé"),
                                  text, time.time())
                else:
                    self.active = self._read(props)
            except Exception:
                pass
            if self._wake.wait(POLL):
                self._wake.clear()

    @staticmethod
    def _read(props):
        return bool(props.Get("org.freedesktop.Notifications", "Inhibited")) or _plasma_until()
