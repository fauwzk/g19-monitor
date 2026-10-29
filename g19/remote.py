"""Clavier G19 virtuel : l'utilitaire envoie des touches à l'appli et affiche en direct
l'écran qu'elle envoie au G19 (fichiers d'échange dans %LOCALAPPDATA%\\G19Monitor)."""
import os
import time

from PIL import Image

from . import config

KEYS_FILE = "virtual_keys.json"      # touches envoyées par l'utilitaire : {"keys": [[n, touche]…]}
MIRROR_REQ = "mirror_request.json"   # l'utilitaire le rafraîchit tant qu'il affiche le direct
MIRROR_FILE = "mirror.bmp"           # dernière image envoyée au G19
MIRROR_TTL = 3                       # s sans demande avant d'arrêter la copie
MIRROR_PERIOD = 0.1                  # au plus 10 images/s copiées

BUTTONS = ("left", "right", "up", "down", "ok", "cancel", "menu")


# --- côté utilitaire ---

def send_key(button):
    data = config.load(KEYS_FILE, {}) or {}
    keys = data.get("keys") or []
    n = (keys[-1][0] if keys else 0) + 1
    config.save(KEYS_FILE, {"keys": (keys + [[n, button]])[-30:]})


def request_mirror():
    config.save(MIRROR_REQ, {"at": time.time()})


def read_mirror(max_age=2):
    """Dernière image du G19, ou None si l'appli n'en copie plus."""
    path = config.DATA_DIR / MIRROR_FILE
    try:
        if time.time() - path.stat().st_mtime > max_age:
            return None
        with Image.open(path) as im:
            return im.convert("RGB")
    except (OSError, ValueError):
        return None


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

    def write(self, img, now):
        if now - self.checked >= 1:
            self.checked = now
            self.req_at = (config.load(MIRROR_REQ, {}) or {}).get("at", 0)
        if now - self.req_at > MIRROR_TTL or now - self.written < MIRROR_PERIOD:
            return
        self.written = now
        path = config.DATA_DIR / MIRROR_FILE
        tmp = path.with_suffix(".tmp")
        try:
            img.convert("RGB").save(tmp, "BMP")
            os.replace(tmp, path)
        except OSError:
            pass
