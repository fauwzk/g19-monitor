"""PC au repos : Windows verrouillé ou aucune entrée depuis un moment. L'écran du G19 passe
alors sur une grande horloge, et tout ce qui arrive pendant l'absence (messages, amis,
agents Claude, téléchargements…) est noté pour un résumé au retour."""
import ctypes
import time
from ctypes import wintypes

user32 = ctypes.WinDLL("user32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32")
powrprof = ctypes.WinDLL("powrprof")

DESKTOP_SWITCHDESKTOP = 0x0100
UOI_NAME = 2
SYSTEM_EXECUTION_STATE = 16
ES_DISPLAY_REQUIRED = 0x00000002

SUMMARY_SECONDS = 45     # le résumé se ferme tout seul après ce temps
MAX_ITEMS = 60
# bandeaux qui ne valent pas une ligne dans le résumé
SKIP_SOURCES = {"Utilitaire", "En jeu", "Ventilos", "Écrans"}


class LASTINPUTINFO(ctypes.Structure):
    _fields_ = [("cbSize", wintypes.UINT), ("dwTime", wintypes.DWORD)]


user32.OpenInputDesktop.restype = wintypes.HANDLE
user32.GetUserObjectInformationW.argtypes = [wintypes.HANDLE, ctypes.c_int, wintypes.LPVOID,
                                             wintypes.DWORD, ctypes.POINTER(wintypes.DWORD)]
user32.CloseDesktop.argtypes = [wintypes.HANDLE]
kernel32.GetTickCount.restype = wintypes.DWORD


def idle_seconds():
    """Temps depuis la dernière entrée clavier / souris sur Windows."""
    info = LASTINPUTINFO(cbSize=ctypes.sizeof(LASTINPUTINFO))
    if not user32.GetLastInputInfo(ctypes.byref(info)):
        return 0.0
    return ((kernel32.GetTickCount() - info.dwTime) & 0xFFFFFFFF) / 1000


def is_locked():
    """Vrai quand l'écran de verrouillage (bureau Winlogon) a remplacé le bureau normal."""
    h = user32.OpenInputDesktop(0, False, DESKTOP_SWITCHDESKTOP)
    if not h:
        return True             # bureau sécurisé : pas accessible depuis la session
    try:
        buf = ctypes.create_unicode_buffer(64)
        n = wintypes.DWORD()
        if not user32.GetUserObjectInformationW(h, UOI_NAME, buf, ctypes.sizeof(buf),
                                                ctypes.byref(n)):
            return False
        return buf.value.lower() != "default"
    finally:
        user32.CloseDesktop(h)


def display_required():
    """Une appli demande à garder l'écran allumé (vidéo en cours de lecture, présentation)."""
    state = wintypes.ULONG()
    if powrprof.CallNtPowerInformation(SYSTEM_EXECUTION_STATE, None, 0, ctypes.byref(state),
                                       ctypes.sizeof(state)):
        return False
    return bool(state.value & ES_DISPLAY_REQUIRED)


class Away:
    def __init__(self):
        self.since = None        # début de l'absence en cours
        self.locked = False
        self.items = []          # [{"source", "title", "body", "color", "icon", "at"}]
        self.summary = None      # (lignes, début, fin, affiché depuis) : résumé au retour
        self._seen = set()
        self._sessions = {}
        self._downloads = {}
        self._poke = time.time()

    @property
    def active(self):
        return self.since is not None

    def poke(self, now=None):
        """Une touche du G19 compte comme une présence (Windows ne la voit pas)."""
        self._poke = now or time.time()

    def close_summary(self):
        self.summary = None

    def update(self, c, now, candidates):
        """Toutes les secondes. `candidates` : les bandeaux connus (render.toast_candidates)."""
        cfg = c.settings
        if self.summary and now - self.summary[3] > SUMMARY_SECONDS:
            self.summary = None
        if not cfg.get("idle_screen", True) and not cfg.get("away_summary", True):
            self.since = None
            return
        try:
            locked = is_locked()
            idle = min(idle_seconds(), now - self._poke)
            busy = bool(c.gpu and c.gpu.game) or display_required()
        except OSError:
            return
        away = locked or (idle >= cfg.get("idle_minutes", 5) * 60 and not busy)
        self.locked = locked
        if away and self.since is None:
            self._start(c, now - (0 if locked else idle), candidates)
        elif not away and self.since is not None:
            self._stop(cfg, now)
        if self.since is not None:
            self._collect(c, candidates)

    def _start(self, c, since, candidates):
        self.since = since
        self.items = []
        self.summary = None
        self._seen = {self._key(n) for n in candidates}
        if c.discord:
            self._seen |= {("Discord", n["author"], n["body"]) for n in list(c.discord.notifications)}
        self._sessions = {s.session_id: s.state for s in c.sessions}
        self._downloads = {dl["appid"]: dl["name"] for dl in (c.steam.downloads if c.steam else [])}

    def _stop(self, cfg, now):
        long_enough = now - self.since >= cfg.get("away_min_minutes", 5) * 60
        if self.items and long_enough and cfg.get("away_summary", True):
            self.summary = (list(self.items), self.since, now, now)
        self.since = None

    @staticmethod
    def _key(n):
        return n["source"], n["title"], n["body"]

    def _add(self, key, item):
        if key in self._seen or len(self.items) >= MAX_ITEMS:
            return
        self._seen.add(key)
        self.items.append(item)

    def _collect(self, c, candidates):
        now = time.time()
        # tous les messages Discord, pas seulement le dernier affiché en bandeau
        if c.discord:
            for n in reversed(list(c.discord.notifications)):   # fil Discord : copie
                self._add(("Discord", n["author"], n["body"]),
                          {"source": "Discord", "title": n["author"], "body": n["body"],
                           "icon": n.get("icon"), "color": "discord", "at": now})
        for n in candidates:
            if n["source"] in SKIP_SOURCES or n["source"] == "Discord":
                continue
            self._add(self._key(n), {**n, "at": n.get("at", now)})
        # agents Claude qui ont fini ou attendent une réponse
        states = {s.session_id: s for s in c.sessions}
        for sid, s in states.items():
            before = self._sessions.get(sid)
            if before == "working" and s.state in ("idle", "waiting"):
                body = "attend une réponse" if s.state == "waiting" else "a fini"
                self._add(("Claude", sid, now), {"source": "Claude", "title": s.name,
                                                 "body": body, "icon": None,
                                                 "color": "claude", "at": now})
        self._sessions = {sid: s.state for sid, s in states.items()}
        # téléchargements Steam disparus de la file : terminés
        downloads = {dl["appid"]: dl["name"] for dl in (c.steam.downloads if c.steam else [])}
        for appid, name in self._downloads.items():
            if appid not in downloads:
                self._add(("Steam dl", appid), {"source": "Steam", "title": name,
                                                "body": "téléchargement terminé", "icon": None,
                                                "color": "steam", "at": now})
        self._downloads = downloads

    def counts(self):
        """{source: nombre} de ce qui est arrivé pendant l'absence en cours."""
        out = {}
        for it in self.items:
            out[it["source"]] = out.get(it["source"], 0) + 1
        return out
