"""Recopie d'un écran du PC sur le G19 (page Écran PC) : capture GDI en tâche de fond, seulement
quand la page est affichée. Windows réduit l'image à la taille du LCD pendant la copie
(StretchBlt) : 2× plus rapide que copier l'écran entier puis le réduire. Zoom autour du
curseur de la souris."""
import ctypes
import threading
import time
from ctypes import wintypes

from PIL import Image

FPS = 60                 # plafond ; la copie GDI (~30 ms) limite en pratique à ~30 i/s
ZOOMS = (1, 2, 4)
SIZE = (320, 214)        # sous la barre du haut
SRCCOPY = 0x00CC0020
HALFTONE = 4             # réduction lissée : texte lisible

user32 = ctypes.WinDLL("user32")
gdi32 = ctypes.WinDLL("gdi32")
user32.GetDC.restype = wintypes.HDC
user32.GetDC.argtypes = [wintypes.HWND]
user32.ReleaseDC.argtypes = [wintypes.HWND, wintypes.HDC]
gdi32.CreateCompatibleDC.restype = wintypes.HDC
gdi32.CreateCompatibleDC.argtypes = [wintypes.HDC]
gdi32.CreateDIBSection.restype = wintypes.HBITMAP
gdi32.CreateDIBSection.argtypes = [wintypes.HDC, ctypes.c_void_p, wintypes.UINT,
                                   ctypes.POINTER(ctypes.c_void_p), wintypes.HANDLE,
                                   wintypes.DWORD]
gdi32.SelectObject.restype = wintypes.HGDIOBJ
gdi32.SelectObject.argtypes = [wintypes.HDC, wintypes.HGDIOBJ]
gdi32.DeleteObject.argtypes = [wintypes.HGDIOBJ]
gdi32.DeleteDC.argtypes = [wintypes.HDC]
gdi32.StretchBlt.argtypes = [wintypes.HDC] + [ctypes.c_int] * 4 + [wintypes.HDC] + \
    [ctypes.c_int] * 4 + [wintypes.DWORD]
gdi32.SetStretchBltMode.argtypes = [wintypes.HDC, ctypes.c_int]
gdi32.SetBrushOrgEx.argtypes = [wintypes.HDC, ctypes.c_int, ctypes.c_int, ctypes.c_void_p]


class BITMAPINFOHEADER(ctypes.Structure):
    _fields_ = [("biSize", wintypes.DWORD), ("biWidth", wintypes.LONG),
                ("biHeight", wintypes.LONG), ("biPlanes", wintypes.WORD),
                ("biBitCount", wintypes.WORD), ("biCompression", wintypes.DWORD),
                ("biSizeImage", wintypes.DWORD), ("biXPelsPerMeter", wintypes.LONG),
                ("biYPelsPerMeter", wintypes.LONG), ("biClrUsed", wintypes.DWORD),
                ("biClrImportant", wintypes.DWORD)]


class Blitter:
    """Image mémoire de taille fixe dans laquelle Windows copie (et réduit) l'écran."""

    def __init__(self, w, h):
        self.size = (w, h)
        self.screen = user32.GetDC(None)        # tout le bureau virtuel
        self.dc = gdi32.CreateCompatibleDC(self.screen)
        bmi = BITMAPINFOHEADER(biSize=ctypes.sizeof(BITMAPINFOHEADER), biWidth=w,
                               biHeight=-h, biPlanes=1, biBitCount=32)
        self.bits = ctypes.c_void_p()
        self.bmp = gdi32.CreateDIBSection(self.dc, ctypes.byref(bmi), 0, ctypes.byref(self.bits),
                                          None, 0)
        if not self.bmp:
            raise OSError("CreateDIBSection")
        self._old = gdi32.SelectObject(self.dc, self.bmp)
        gdi32.SetStretchBltMode(self.dc, HALFTONE)
        gdi32.SetBrushOrgEx(self.dc, 0, 0, None)

    def grab(self, x, y, w, h):
        dw, dh = self.size
        # sans CAPTUREBLT : inutile avec la composition de Windows 10/11, et fait clignoter le curseur
        if not gdi32.StretchBlt(self.dc, 0, 0, dw, dh, self.screen, x, y, w, h, SRCCOPY):
            raise OSError("StretchBlt")
        return Image.frombuffer("RGB", self.size, ctypes.string_at(self.bits, dw * dh * 4),
                                "raw", "BGRX", 0, 1)

    def close(self):
        gdi32.SelectObject(self.dc, self._old)
        gdi32.DeleteObject(self.bmp)
        gdi32.DeleteDC(self.dc)
        user32.ReleaseDC(None, self.screen)
MONITORENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HMONITOR, wintypes.HDC,
                                     ctypes.POINTER(wintypes.RECT), wintypes.LPARAM)


class MONITORINFO(ctypes.Structure):
    _fields_ = [("cbSize", wintypes.DWORD), ("rcMonitor", wintypes.RECT),
                ("rcWork", wintypes.RECT), ("dwFlags", wintypes.DWORD)]


def monitors():
    """[(gauche, haut, droite, bas, principal ?)], l'écran principal en premier puis de gauche
    à droite."""
    out = []

    def cb(hmon, _hdc, _rect, _lp):
        info = MONITORINFO(cbSize=ctypes.sizeof(MONITORINFO))
        user32.GetMonitorInfoW(hmon, ctypes.byref(info))
        r = info.rcMonitor
        out.append((r.left, r.top, r.right, r.bottom, bool(info.dwFlags & 1)))
        return True

    user32.EnumDisplayMonitors(None, None, MONITORENUMPROC(cb), 0)
    out.sort(key=lambda m: (not m[4], m[0]))
    return out


def cursor_pos():
    p = wintypes.POINT()
    user32.GetCursorPos(ctypes.byref(p))
    return p.x, p.y


class ScreenMirror:
    def __init__(self):
        self.frame = None        # dernière image (RGB, ≤ SIZE)
        self.cursor = None       # position du curseur dans l'image, None s'il est ailleurs
        self.screen = 0          # écran recopié (0 = principal)
        self.count = 1
        self.zoom = 0            # indice dans ZOOMS
        self.label = ""
        self.status = ""
        self.fps = 0.0           # images capturées par seconde, réellement
        self._wanted = 0.0
        threading.Thread(target=self._run, daemon=True).start()

    def want(self):
        """Appelé à chaque image de la page : la capture ne tourne que quand on la regarde."""
        self._wanted = time.time()

    def next_screen(self):
        self.screen = (self.screen + 1) % max(1, self.count)

    def zoom_in(self, step):
        self.zoom = max(0, min(len(ZOOMS) - 1, self.zoom + step))

    def _run(self):
        try:   # coordonnées réelles en pixels, même avec une mise à l'échelle Windows
            user32.SetThreadDpiAwarenessContext(ctypes.c_void_p(-4))
        except (AttributeError, OSError):
            pass
        mons, mons_at = [], 0.0
        blit = None
        frames, fps_at = 0, time.time()
        while True:
            start = time.time()
            if start - self._wanted > 1.0:
                if blit:                 # page quittée : on rend les ressources GDI
                    blit.close()
                    blit = None
                time.sleep(0.2)
                continue
            if start - mons_at > 5:
                mons, mons_at = monitors(), start
                self.count = len(mons)
            try:
                blit = self._grab(mons[self.screen % len(mons)] if mons else None, blit)
                self.status = ""
                frames += 1
            except Exception as e:      # écran verrouillé, bureau sécurisé…
                self.status = f"capture impossible ({e.__class__.__name__})"
                if blit:
                    blit.close()
                    blit = None
                time.sleep(0.5)
            if start - fps_at >= 2:
                self.fps, frames, fps_at = frames / (start - fps_at), 0, start
            time.sleep(max(0.0, 1 / FPS - (time.time() - start)))

    def _grab(self, mon, blit):
        left, top, right, bottom = mon[:4] if mon else (0, 0, 1920, 1080)
        z = ZOOMS[self.zoom]
        cx, cy = cursor_pos()
        w, h = (right - left) // z, (bottom - top) // z
        x0, y0 = left, top
        if z > 1:   # fenêtre centrée sur le curseur, gardée dans l'écran
            x0 = int(min(max(cx - w / 2, left), right - w))
            y0 = int(min(max(cy - h / 2, top), bottom - h))
        scale = min(SIZE[0] / w, SIZE[1] / h)
        size = (max(1, round(w * scale)), max(1, round(h * scale)))
        if not blit or blit.size != size:
            if blit:
                blit.close()
            blit = Blitter(*size)
        self.frame = blit.grab(x0, y0, w, h)
        inside = x0 <= cx < x0 + w and y0 <= cy < y0 + h
        self.cursor = ((cx - x0) * scale, (cy - y0) * scale) if inside else None
        self.label = f"{'principal' if mon and mon[4] else f'écran {self.screen + 1}'}"                      f" · {right - left}×{bottom - top}" + (f" · zoom ×{z}" if z > 1 else "")
        return blit
