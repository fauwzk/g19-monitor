"""Rétroéclairage du G19 sous Linux, à la place du SDK LED de Logitech (LogitechLed.dll) :
mêmes fonctions (LogiLedSetLighting, LogiLedFlashLighting…), que backlight.py appelle telles
quelles. La couleur part au clavier en rapport HID « feature » n° 7 [7, r, g, b] sur l'interface
1 du clavier (046d:c228), via /dev/hidraw (règle udev installer/linux/99-g19.rules) ;
clignotement et pulsation sont animés par un fil, le clavier ne sait faire qu'une couleur fixe.
Format connu par rétro-ingénierie (projets libres autour du G19)."""
import fcntl
import glob
import math
import os
import threading
import time

REPORT = 7
TICK = 0.03


def _sfeature(n):            # HIDIOCSFEATURE(len)
    return (3 << 30) | (n << 16) | (ord("H") << 8) | 6


def find_hidraw():
    for h in sorted(glob.glob("/sys/class/hidraw/hidraw*")):
        try:
            with open(h + "/device/uevent") as f:
                ue = f.read().upper()
        except OSError:
            continue
        iface = os.path.basename(os.path.dirname(os.path.realpath(h + "/device")))
        if "0000046D:0000C228" in ue and iface.endswith(":1.1"):
            return "/dev/" + os.path.basename(h)
    return None


class G19Led:
    def __init__(self):
        self._fd = None
        self._effect = None        # ("flash" | "pulse", (r, g, b), période s, début)
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._last = None

    # --- envoi ---

    def _send(self, rgb):
        rgb = tuple(max(0, min(255, int(round(v * 2.55)))) for v in rgb)
        if rgb == self._last:
            return True
        try:
            fcntl.ioctl(self._fd, _sfeature(4), bytes([REPORT, *rgb]))
        except OSError:
            return False
        self._last = rgb
        return True

    def _run(self):
        while not self._stop.wait(TICK):
            with self._lock:
                eff = self._effect
            if not eff:
                continue
            kind, rgb, period, start = eff
            phase = ((time.time() - start) / period) % 1
            if kind == "flash":
                k = 1.0 if phase < 0.5 else 0.0
            else:                  # pulsation douce
                k = 0.15 + 0.85 * (0.5 - 0.5 * math.cos(2 * math.pi * phase))
            self._send(tuple(v * k for v in rgb))

    # --- interface du SDK LED ---

    def LogiLedInit(self):
        dev = find_hidraw()
        if not dev:
            return False
        try:
            self._fd = os.open(dev, os.O_RDWR)
        except OSError:
            return False
        threading.Thread(target=self._run, daemon=True, name="rétroéclairage G19").start()
        return True

    def LogiLedSetTargetDevice(self, _device):
        return True

    def LogiLedSaveCurrentLighting(self):
        return True                # le clavier ne dit pas sa couleur : rien à garder

    def LogiLedRestoreLighting(self):
        return self.LogiLedSetLighting(100, 100, 100)

    def LogiLedStopEffects(self):
        with self._lock:
            self._effect = None
        return True

    def LogiLedSetLighting(self, r, g, b):
        self.LogiLedStopEffects()
        return self._send((r, g, b))

    def _animate(self, kind, r, g, b, interval_ms):
        with self._lock:
            self._effect = (kind, (r, g, b), max(0.1, (interval_ms or 500) / 1000), time.time())
        return self._fd is not None

    def LogiLedFlashLighting(self, r, g, b, _duration, interval_ms):
        return self._animate("flash", r, g, b, interval_ms)

    def LogiLedPulseLighting(self, r, g, b, _duration, interval_ms):
        return self._animate("pulse", r, g, b, interval_ms)

    def LogiLedShutdown(self):
        self._stop.set()
        if self._fd is not None:
            try:
                os.close(self._fd)
            except OSError:
                pass
            self._fd = None
