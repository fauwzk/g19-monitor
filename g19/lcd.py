"""Wrapper ctypes autour du Logitech LCD SDK (LogitechLcd.dll) : écran couleur du G19
(G19LCD) et écran monochrome 160×43 des G15 / G510 / G13 (MonoLCD).

Le SDK passe par Logitech Gaming Software (LCore.exe), qui doit tourner.
"""
import ctypes
import os

W, H = 320, 240
LCD_TYPE_COLOR = 2

BUTTONS = {
    "left": 0x0100,
    "right": 0x0200,
    "ok": 0x0400,
    "cancel": 0x0800,
    "up": 0x1000,
    "down": 0x2000,
    "menu": 0x4000,
}

DLL_CANDIDATES = [
    os.environ.get("G19_LCD_DLL", ""),
    r"C:\Program Files\Logitech Gaming Software\SDK\LCD\x64\LogitechLcd.dll",
    r"C:\Program Files\Logitech Gaming Software\LCDSDK\Lib\x64\LogitechLcd.dll",
]


def _load_dll():
    for path in DLL_CANDIDATES:
        if path and os.path.isfile(path):
            return ctypes.CDLL(path)
    raise FileNotFoundError("LogitechLcd.dll introuvable (définir G19_LCD_DLL)")


class G19LCD:
    def __init__(self, name="PC Monitor"):
        dll = self.dll = _load_dll()
        dll.LogiLcdInit.argtypes = [ctypes.c_wchar_p, ctypes.c_int]
        dll.LogiLcdInit.restype = ctypes.c_bool
        dll.LogiLcdIsConnected.argtypes = [ctypes.c_int]
        dll.LogiLcdIsConnected.restype = ctypes.c_bool
        dll.LogiLcdIsButtonPressed.argtypes = [ctypes.c_int]
        dll.LogiLcdIsButtonPressed.restype = ctypes.c_bool
        dll.LogiLcdColorSetBackground.argtypes = [ctypes.POINTER(ctypes.c_ubyte)]
        dll.LogiLcdColorSetBackground.restype = ctypes.c_bool
        dll.LogiLcdUpdate.restype = None
        dll.LogiLcdShutdown.restype = None

        if not dll.LogiLcdInit(name, LCD_TYPE_COLOR):
            raise RuntimeError("LogiLcdInit a échoué (Logitech Gaming Software lancé ?)")
        self._buf = (ctypes.c_ubyte * (W * H * 4))()
        self._last = None
        self._held = set()
        self.sent = 0           # images réellement envoyées (pour mesurer la fluidité)

    def connected(self):
        return self.dll.LogiLcdIsConnected(LCD_TYPE_COLOR)

    def show(self, img):
        """Envoie une image PIL 320x240 (convertie en BGRA), sauf si elle n'a pas changé."""
        data = img.convert("RGBA").tobytes("raw", "BGRA")
        if data == self._last:
            return
        self._last = data
        ctypes.memmove(self._buf, data, len(data))
        self.dll.LogiLcdColorSetBackground(self._buf)
        self.sent += 1

    def update(self):
        self.dll.LogiLcdUpdate()

    def pressed(self):
        """Boutons nouvellement enfoncés depuis le dernier appel (détection de front)."""
        held = {n for n, m in BUTTONS.items() if self.dll.LogiLcdIsButtonPressed(m)}
        new = held - self._held
        self._held = held
        return new

    def close(self):
        self.dll.LogiLcdShutdown()


# --- écran monochrome (G15, G510, G13…) -------------------------------------------------------

MONO_W, MONO_H = 160, 43
LCD_TYPE_MONO = 1
MONO_BUTTONS = {"b1": 0x01, "b2": 0x02, "b3": 0x04, "b4": 0x08}   # 4 touches sous l'écran


class MonoLCD:
    """Écran monochrome : une applet à part (un autre nom), qui tourne en même temps que celle
    du G19 ; Logitech Gaming Software l'affiche sur le clavier monochrome."""

    def __init__(self, name="PC Monitor (G15)"):
        dll = self.dll = _load_dll()
        dll.LogiLcdInit.argtypes = [ctypes.c_wchar_p, ctypes.c_int]
        dll.LogiLcdInit.restype = ctypes.c_bool
        dll.LogiLcdIsConnected.argtypes = [ctypes.c_int]
        dll.LogiLcdIsConnected.restype = ctypes.c_bool
        dll.LogiLcdIsButtonPressed.argtypes = [ctypes.c_int]
        dll.LogiLcdIsButtonPressed.restype = ctypes.c_bool
        dll.LogiLcdMonoSetBackground.argtypes = [ctypes.POINTER(ctypes.c_ubyte)]
        dll.LogiLcdMonoSetBackground.restype = ctypes.c_bool
        dll.LogiLcdUpdate.restype = None
        dll.LogiLcdShutdown.restype = None
        if not dll.LogiLcdInit(name, LCD_TYPE_MONO):
            raise RuntimeError("LogiLcdInit a échoué (Logitech Gaming Software lancé ?)")
        self._buf = (ctypes.c_ubyte * (MONO_W * MONO_H))()
        self._last = None
        self._held = set()

    def connected(self):
        return self.dll.LogiLcdIsConnected(LCD_TYPE_MONO)

    def show(self, img):
        """Image PIL 160×43 (mode "1" ou gris) : un octet par pixel, allumé au-delà de 128."""
        data = img.convert("L").point(lambda v: 255 if v >= 128 else 0).tobytes()
        if data == self._last:
            return
        self._last = data
        ctypes.memmove(self._buf, data, len(data))
        self.dll.LogiLcdMonoSetBackground(self._buf)

    def update(self):
        self.dll.LogiLcdUpdate()

    def pressed(self):
        held = {n for n, m in MONO_BUTTONS.items() if self.dll.LogiLcdIsButtonPressed(m)}
        new = held - self._held
        self._held = held
        return new

    def close(self):
        self.dll.LogiLcdShutdown()
