"""Clavier G19 virtuel : l'utilitaire envoie des touches à l'appli (fichiers d'échange dans
%LOCALAPPDATA%\\G19Monitor) et affiche en direct l'écran du G19, copié dans une mémoire
partagée (pas de fichier : jusqu'à 60 images/s sans écrire sur le disque)."""
import mmap
import struct
import time

from PIL import Image

from . import config

KEYS_FILE = "virtual_keys.json"      # touches envoyées par l'utilitaire : {"keys": [[n, touche]…]}
MIRROR_REQ = "mirror_request.json"   # l'utilitaire le rafraîchit tant qu'il affiche le direct
MIRROR_TTL = 3                       # s sans demande avant d'arrêter la copie
MIRROR_FPS = 60                      # images/s copiées pour l'aperçu de l'utilitaire
MIRROR_NAME = "G19MonitorMirror"     # mémoire partagée : en-tête puis image 320×240 RGB
MIRROR_HEAD = struct.Struct("<dQ")   # horodatage, numéro d'image
MIRROR_W, MIRROR_H = 320, 240
MIRROR_SIZE = MIRROR_HEAD.size + MIRROR_W * MIRROR_H * 3


STATS_NAME = "G19MonitorStats"       # mémoire partagée : fluidité réelle du G19
STATS_HEAD = struct.Struct("<ddd")   # horodatage, images/s envoyées au G19, réglage


def _stats_mem():
    try:
        return mmap.mmap(-1, STATS_HEAD.size, tagname=STATS_NAME)
    except (OSError, ValueError):
        return None


_stats = {"mem": None}


def publish_fps(fps, target):
    """Côté appli : images/s réellement envoyées au G19 (toutes les 2 s)."""
    if _stats["mem"] is None:
        _stats["mem"] = _stats_mem()
    if _stats["mem"] is not None:
        STATS_HEAD.pack_into(_stats["mem"], 0, time.time(), float(fps), float(target))


def read_fps(max_age=5):
    """Côté utilitaire : (images/s du G19, réglage), None si l'appli ne publie plus."""
    if _stats["mem"] is None:
        _stats["mem"] = _stats_mem()
        if _stats["mem"] is None:
            return None
    at, fps, target = STATS_HEAD.unpack_from(_stats["mem"], 0)
    if time.time() - at > max_age:
        return None
    return fps, target


def _shared():
    """Mémoire partagée de l'aperçu (créée par le premier des deux processus qui l'ouvre)."""
    try:
        return mmap.mmap(-1, MIRROR_SIZE, tagname=MIRROR_NAME)
    except (OSError, ValueError):
        return None

BUTTONS = ("left", "right", "up", "down", "ok", "cancel", "menu")


# --- côté utilitaire ---

def send_key(button):
    data = config.load(KEYS_FILE, {}) or {}
    keys = data.get("keys") or []
    n = (keys[-1][0] if keys else 0) + 1
    config.save(KEYS_FILE, {"keys": (keys + [[n, button]])[-30:]})


def request_mirror():
    config.save(MIRROR_REQ, {"at": time.time()})


class MirrorReader:
    """Côté utilitaire : la dernière image copiée par l'appli, seulement quand elle a changé."""

    def __init__(self):
        self._mem = None
        self.frame = -1

    def read(self, max_age=2):
        """Nouvelle image (PIL) ; None si rien de neuf ou si l'appli n'en copie plus."""
        if self._mem is None:
            self._mem = _shared()
            if self._mem is None:
                return None
        at, n = MIRROR_HEAD.unpack_from(self._mem, 0)
        if n == self.frame or time.time() - at > max_age:
            return None
        self.frame = n
        data = self._mem[MIRROR_HEAD.size:MIRROR_SIZE]
        return Image.frombytes("RGB", (MIRROR_W, MIRROR_H), data)

    def live(self, max_age=2):
        """L'appli copie-t-elle encore des images ?"""
        if self._mem is None:
            return False
        at, _n = MIRROR_HEAD.unpack_from(self._mem, 0)
        return time.time() - at <= max_age


# --- côté appli ---

class KeyInbox:
    """Touches virtuelles reçues depuis le dernier appel (les anciennes sont ignorées)."""

    def __init__(self):
        self.path = config.DATA_DIR / KEYS_FILE
        self.mtime = self._mtime()
        self.last = self._max(config.load(KEYS_FILE, {}) or {})

    def _mtime(self):
        try:
            return self.path.stat().st_mtime
        except OSError:
            return 0

    @staticmethod
    def _max(data):
        keys = data.get("keys") or []
        return keys[-1][0] if keys else 0

    def pressed(self):
        m = self._mtime()
        if m == self.mtime:
            return []
        self.mtime = m
        data = config.load(KEYS_FILE, {}) or {}
        new = [b for n, b in data.get("keys") or [] if n > self.last and b in BUTTONS]
        self.last = max(self.last, self._max(data))
        return new


class Mirror:
    """Copie l'image du G19 pour l'utilitaire, seulement tant qu'il la demande."""

    def __init__(self):
        self.req_at = 0.0
        self.checked = 0.0
        self.written = 0.0
        self.count = 0
        self._mem = None

    def active(self, now):
        """L'utilitaire affiche-t-il le direct ? (relu au plus une fois par seconde)"""
        if now - self.checked >= 1:
            self.checked = now
            self.req_at = (config.load(MIRROR_REQ, {}) or {}).get("at", 0)
        return now - self.req_at <= MIRROR_TTL

    def write(self, img, now):
        if not self.active(now) or now - self.written < 1 / MIRROR_FPS * 0.9:
            return
        if self._mem is None:
            self._mem = _shared()
            if self._mem is None:
                return
        self.written = now
        self.count += 1
        rgb = img.convert("RGB")
        if rgb.size != (MIRROR_W, MIRROR_H):
            rgb = rgb.resize((MIRROR_W, MIRROR_H))
        self._mem[MIRROR_HEAD.size:MIRROR_SIZE] = rgb.tobytes()
        MIRROR_HEAD.pack_into(self._mem, 0, now, self.count)   # en dernier : image complète
