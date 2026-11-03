"""Présence devant le PC sous Linux, pour l'écran de repos (away.py) et « Ne pas déranger » :
  - verrouillé : org.freedesktop.ScreenSaver (KDE, GNOME), sinon LockedHint de logind ;
  - inactif : IdleHint / IdleSinceHint de logind (Wayland ne donne pas le temps depuis la
    dernière touche aux applis) ;
  - écran gardé allumé (vidéo…) : inhibitions de org.freedesktop.PowerManagement."""
import os
import time

_bus = {}


def _dbus():
    import dbus
    return dbus


def _session_bus():
    if "session" not in _bus:
        _bus["session"] = _dbus().SessionBus()
    return _bus["session"]


def _login_session():
    """Propriétés de la session graphique de l'utilisateur dans logind."""
    dbus = _dbus()
    if "login" not in _bus:
        sysbus = dbus.SystemBus()
        mgr = dbus.Interface(sysbus.get_object("org.freedesktop.login1",
                                               "/org/freedesktop/login1"),
                             "org.freedesktop.login1.Manager")
        path = None
        for sid, uid, _user, seat, p in mgr.ListSessions():
            if int(uid) == os.getuid() and (seat == "seat0" or path is None):
                path = p
        if path is None:
            raise OSError("pas de session logind")
        _bus["login"] = dbus.Interface(sysbus.get_object("org.freedesktop.login1", path),
                                       "org.freedesktop.DBus.Properties")
    return _bus["login"]


def idle_seconds():
    try:
        props = _login_session()
        if bool(props.Get("org.freedesktop.login1.Session", "IdleHint")):
            since = int(props.Get("org.freedesktop.login1.Session", "IdleSinceHint")) / 1e6
            return max(0.0, time.time() - since) if since else 3600.0
    except Exception:
        _bus.pop("login", None)
    return 0.0


def is_locked():
    try:
        obj = _session_bus().get_object("org.freedesktop.ScreenSaver", "/ScreenSaver")
        if bool(obj.GetActive(dbus_interface="org.freedesktop.ScreenSaver")):
            return True
    except Exception:
        _bus.pop("session", None)
    try:
        return bool(_login_session().Get("org.freedesktop.login1.Session", "LockedHint"))
    except Exception:
        _bus.pop("login", None)
        return False


def display_required():
    try:
        obj = _session_bus().get_object("org.freedesktop.PowerManagement",
                                        "/org/freedesktop/PowerManagement/Inhibit")
        return bool(obj.HasInhibit(dbus_interface="org.freedesktop.PowerManagement.Inhibit"))
    except Exception:
        return False
