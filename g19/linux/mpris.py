"""Média en cours sous Linux via MPRIS (D-Bus) : Spotify, Firefox, Chromium, VLC, mpv…
Même interface que media.MediaMonitor (state, command) : la page Média, les paroles, les
bandeaux et le bilan s'en servent tels quels."""
import threading
import time
import urllib.parse
import urllib.request

from ..media import MediaState, _prepare_art

PREFIX = "org.mpris.MediaPlayer2."
PLAYER = "org.mpris.MediaPlayer2.Player"
PROPS = "org.freedesktop.DBus.Properties"
POLL = 0.5                 # s entre deux lectures
NAMES = {"spotify": "Spotify", "firefox": "Firefox", "chromium": "Chromium",
         "chrome": "Chrome", "vlc": "VLC", "mpv": "mpv", "elisa": "Elisa",
         "strawberry": "Strawberry", "rhythmbox": "Rhythmbox", "plasma-browser-integration":
         "Navigateur", "kdeconnect": "Téléphone"}


def _app(bus_name, identity):
    low = bus_name[len(PREFIX):].lower()
    for key, name in NAMES.items():
        if low.startswith(key):
            return name
    return identity or low.split(".")[0].capitalize()


def _art_bytes(url):
    if not url:
        return None
    if url.startswith("file://"):
        with open(urllib.parse.unquote(url[7:]), "rb") as f:
            return f.read()
    if url.startswith(("http://", "https://")):
        req = urllib.request.Request(url, headers={"User-Agent": "G19Monitor"})
        with urllib.request.urlopen(req, timeout=6) as r:
            return r.read()
    return None


class MprisMonitor:
    def __init__(self):
        self.state = None
        self._player = None        # nom D-Bus du lecteur suivi
        self._art_key, self._art = None, (None, None, None)
        self._seen = {}            # lecteur → dernière fois vu en lecture
        self._lock = threading.Lock()
        try:
            import dbus
            self._dbus = dbus
            self._bus = dbus.SessionBus()
        except Exception:          # pas de bus de session (SSH sans bureau…)
            self._bus = None
            return
        threading.Thread(target=self._run, daemon=True, name="mpris").start()

    def _props(self, name):
        obj = self._bus.get_object(name, "/org/mpris/MediaPlayer2")
        return self._dbus.Interface(obj, PROPS)

    def _pick(self, players):
        """Le lecteur qui joue (le plus récemment vu en lecture), sinon le dernier suivi."""
        now = time.time()
        playing = []
        for name in players:
            try:
                status = str(self._props(name).Get(PLAYER, "PlaybackStatus"))
            except self._dbus.DBusException:
                continue
            if status == "Playing":
                self._seen[name] = now
                playing.append(name)
        if playing:
            return max(playing, key=lambda n: self._seen.get(n, 0))
        if self._player in players:
            return self._player
        return max(players, key=lambda n: self._seen.get(n, 0)) if players else None

    def _run(self):
        while True:
            try:
                self.state = self._snapshot()
            except Exception:
                self.state = None
            time.sleep(POLL)

    def _snapshot(self):
        players = [str(n) for n in self._bus.list_names() if str(n).startswith(PREFIX)]
        name = self._player = self._pick(players)
        if not name:
            return None
        props = self._props(name)
        p = props.GetAll(PLAYER)
        meta = p.get("Metadata") or {}
        title = str(meta.get("xesam:title") or "")
        if not title:
            return None
        artists = meta.get("xesam:artist") or []
        artist = ", ".join(str(a) for a in artists) if isinstance(artists, (list, tuple)) \
            else str(artists)
        try:
            identity = str(props.Get("org.mpris.MediaPlayer2", "Identity"))
        except self._dbus.DBusException:
            identity = ""
        key = (name, title, artist)
        if key != self._art_key:
            self._art_key, self._art = key, (None, None, None)
            try:
                data = _art_bytes(str(meta.get("mpris:artUrl") or ""))
                if data:
                    self._art = _prepare_art(data)
            except Exception:
                pass
        length = int(meta.get("mpris:length") or 0) / 1e6
        try:
            position = int(props.Get(PLAYER, "Position")) / 1e6
        except (self._dbus.DBusException, TypeError, ValueError):
            position = 0.0
        return MediaState(title=title, artist=artist, album=str(meta.get("xesam:album") or ""),
                          app=_app(name, identity),
                          playing=str(p.get("PlaybackStatus")) == "Playing",
                          position=position, duration=max(length, 0.0), stamp=time.time(),
                          art=self._art[0], bg=self._art[1], accent=self._art[2],
                          estimated=length <= 0)

    def command(self, cmd):
        """'toggle', 'next' ou 'previous' sur le lecteur suivi."""
        name = self._player
        if not name or not self._bus:
            return
        method = {"toggle": "PlayPause", "next": "Next", "previous": "Previous"}[cmd]

        def run():
            try:
                obj = self._bus.get_object(name, "/org/mpris/MediaPlayer2")
                getattr(self._dbus.Interface(obj, PLAYER), method)()
            except Exception:
                pass

        threading.Thread(target=run, daemon=True).start()
