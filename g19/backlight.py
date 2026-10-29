"""Rétroéclairage du G19 comme voyant (Logitech LED SDK, via Logitech Gaming Software).

Après un effet, le clavier repasse dans sa couleur de repos (blanc par défaut, réglable). Sans
couleur de repos, l'éclairage sauvegardé avant le premier effet est réappliqué — mais le SDK
peut sauvegarder la dernière couleur qu'il a lui-même posée, d'où la couleur fixe par défaut.
La connexion au SDK reste ouverte : la couper ferait aussi disparaître l'appli de l'écran LCD.
Dans LGS, l'option « Autoriser les jeux à contrôler l'éclairage » doit être active.
"""
import ctypes
import logging
import os
import threading
import time
from collections import deque

log = logging.getLogger("g19")

DLL = os.environ.get("G19_LED_DLL",
                     r"C:\Program Files\Logitech Gaming Software\SDK\LED\x64\LogitechLed.dll")
DEVICE_RGB = 0x2 | 0x1     # LOGI_DEVICETYPE_RGB | MONOCHROME
INFINITE = 0
RETRY = 2                   # s avant de retenter une initialisation ratée
TICK = 0.02                 # s entre deux pas de l'animation

# état → (effet, r, g, b en %, intervalle ms)
EFFECTS = {
    "alert": ("flash", 100, 0, 0, 300),
    "waiting": ("pulse", 100, 65, 0, None),  # None : suit la vitesse de pulsation réglée
    "working": ("solid", 100, 40, 0, 0),
    "done": ("blink", 0, 100, 20, 0),
    "discord": ("blink", 35, 40, 100, 0),
    "notif": ("blink", 100, 100, 100, 0),
}
BLINK_PERIOD = 300          # ms pour un clignotement (allumé puis éteint)


class Backlight:
    """`update()` et `flash()` ne font que noter ce qui est voulu ; un fil dédié pilote le
    clavier, pour que les animations ne dépendent pas de la fluidité de l'écran."""

    def __init__(self):
        self.speed_ms = BLINK_PERIOD
        self.pulse_ms = BLINK_PERIOD   # pulsation jaune (« Claude attend »)
        self.colors = {}               # état → (r, g, b) en % réglés par l'utilisateur
        self.base = (100, 100, 100)  # couleur de repos en %, None = éclairage sauvegardé
        self._target = None         # état voulu par l'appli
        self._enabled = True
        self._flash = None          # clignotement en cours : (type, début, nombre, période s)
        self._queue = deque(maxlen=4)  # clignotements en attente (joués les uns après les autres)
        self._saved = False         # éclairage du profil sauvegardé, à réappliquer
        self._dll = None            # chargée une fois
        self._active = False        # connexion SDK ouverte (on contrôle l'éclairage)
        self._key = None            # (état, vitesse) déjà appliqué
        self._state = None
        self._next_try = 0.0
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    # --- côté appli ---

    def flash(self, kind, count=3, period_ms=BLINK_PERIOD):
        """`count` clignotements : 'done' (Claude a fini), 'discord' ou 'notif'. Si un
        clignotement est déjà en cours, celui-ci suit."""
        if count > 0:
            with self._lock:
                self._queue.append((kind, count, period_ms / 1000))

    def update(self, state, enabled=True):
        """state : 'alert', 'waiting', 'working' ou None (éclairage normal). `enabled` False
        rend la main à LGS."""
        with self._lock:
            self._target, self._enabled = state, enabled
            if not enabled:
                self._flash = None
                self._queue.clear()

    def close(self):
        self._stop.set()
        self._thread.join(timeout=2)
        self._release()

    # --- fil du clavier ---

    def _wanted(self):
        with self._lock:
            state = self._target if self._enabled else None
            now = time.time()
            if self._flash and (now - self._flash[1]) / self._flash[3] >= self._flash[2]:
                self._flash = None
            if not self._flash and self._queue:
                kind, count, period = self._queue.popleft()
                self._flash = (kind, now, count, period)
                log.info("clignotement : %s ×%d", kind, count)
            if self._flash:
                kind, start, count, period = self._flash
                phase = (now - start) / period
                if state != "alert":  # un clignotement passe devant tout sauf une alerte
                    state = (kind, phase % 1 < 0.5)  # allumé la 1re moitié de chaque période
        return state

    def _run(self):
        while not self._stop.is_set():
            try:
                self._apply(self._wanted())
            except OSError:
                self._active = False
            self._stop.wait(TICK)

    def _load(self):
        if self._dll is None:
            dll = ctypes.CDLL(DLL)
            for fn in ("LogiLedInit", "LogiLedStopEffects", "LogiLedSaveCurrentLighting",
                       "LogiLedRestoreLighting"):
                getattr(dll, fn).restype = ctypes.c_bool
            dll.LogiLedSetTargetDevice.argtypes = [ctypes.c_int]
            dll.LogiLedSetLighting.argtypes = [ctypes.c_int] * 3
            dll.LogiLedFlashLighting.argtypes = [ctypes.c_int] * 5
            dll.LogiLedPulseLighting.argtypes = [ctypes.c_int] * 5
            self._dll = dll
        return self._dll

    def _acquire(self):
        if self._active:
            return True
        if time.time() < self._next_try:
            return False
        try:
            d = self._load()
        except OSError:
            self._next_try = time.time() + 30
            return False
        if not d.LogiLedInit():
            self._next_try = time.time() + RETRY
            return False
        time.sleep(0.3)  # LGS a besoin d'un instant avant d'accepter les commandes
        d.LogiLedSetTargetDevice(DEVICE_RGB)
        self._active = True
        return True

    def _restore(self):
        """Couleur de repos, ou éclairage sauvegardé avant le premier effet."""
        if not self._active:
            return
        if self.base:
            self._dll.LogiLedSetLighting(*self.base)
        elif self._saved:
            self._dll.LogiLedRestoreLighting()
            self._saved = False

    def _release(self):
        """À la fermeture : éclairage d'origine, puis déconnexion du SDK."""
        if self._active:
            try:
                self._dll.LogiLedStopEffects()
                time.sleep(0.15)
                self._restore()
                time.sleep(0.2)
                self._dll.LogiLedShutdown()
            except OSError:
                pass
            self._active = False

    def _apply(self, state):
        name = state[0] if isinstance(state, tuple) else state
        key = (state, self.pulse_ms if state == "waiting" else self.base if state is None
               else None, self.colors.get(name))
        if key == self._key:
            return
        if not isinstance(state, tuple) and not isinstance(self._state, tuple):
            log.info("rétroéclairage : %s", state or "normal")
        if state is not None and not self._acquire():
            return
        prev, self._key, self._state = self._state, key, state
        if not self._active:
            return
        d = self._dll
        if prev in EFFECTS and EFFECTS[prev][0] in ("flash", "pulse"):
            # l'arrêt d'un effet est traité en différé par LGS, qui écraserait une couleur
            # posée juste après
            d.LogiLedStopEffects()
            time.sleep(0.15)
        if state is None:
            self._restore()
            return
        if not self._saved:
            # l'éclairage de l'utilisateur, tel qu'il est juste avant notre premier effet
            d.LogiLedSaveCurrentLighting()
            self._saved = True
        if isinstance(state, tuple):  # clignotement : couleur / éteint
            name, on = state
            _kind, r, g, b, _ = EFFECTS[name]
            r, g, b = self.colors.get(name) or (r, g, b)
            d.LogiLedSetLighting(*((r, g, b) if on else (0, 0, 0)))
            return
        kind, r, g, b, interval = EFFECTS[state]
        r, g, b = self.colors.get(state) or (r, g, b)
        interval = interval or self.pulse_ms
        if kind == "solid":
            d.LogiLedSetLighting(r, g, b)
        elif kind == "flash":
            d.LogiLedFlashLighting(r, g, b, INFINITE, interval)
        else:
            d.LogiLedPulseLighting(r, g, b, INFINITE, interval)
