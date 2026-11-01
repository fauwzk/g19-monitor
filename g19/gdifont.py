"""Texte net en 1 bit, rendu par Windows (GDI) plutôt que par FreeType : sans lissage, GDI
applique les consignes de rendu des polices (« hinting ») et donne l'aspect classique des
petits caractères de Windows, bien plus lisible que FreeType sans lissage. Sert à l'écran
monochrome 160×43 (mono.py)."""
import ctypes
from ctypes import wintypes
from functools import lru_cache

from PIL import Image

_gdi = ctypes.WinDLL("gdi32")
_user = ctypes.WinDLL("user32")

FW_NORMAL, FW_BOLD = 400, 700
NONANTIALIASED_QUALITY = 3
DIB_RGB_COLORS = 0
TRANSPARENT = 1

_gdi.CreateFontW.restype = wintypes.HFONT
_gdi.CreateFontW.argtypes = [ctypes.c_int] * 5 + [wintypes.DWORD] * 8 + [wintypes.LPCWSTR]
_gdi.CreateCompatibleDC.restype = wintypes.HDC
_gdi.CreateCompatibleDC.argtypes = [wintypes.HDC]
_gdi.SelectObject.restype = wintypes.HGDIOBJ
_gdi.SelectObject.argtypes = [wintypes.HDC, wintypes.HGDIOBJ]
_gdi.DeleteObject.argtypes = [wintypes.HGDIOBJ]
_gdi.DeleteDC.argtypes = [wintypes.HDC]
_gdi.SetTextColor.argtypes = [wintypes.HDC, wintypes.COLORREF]
_gdi.SetBkMode.argtypes = [wintypes.HDC, ctypes.c_int]
_gdi.TextOutW.argtypes = [wintypes.HDC, ctypes.c_int, ctypes.c_int, wintypes.LPCWSTR,
                          ctypes.c_int]
_gdi.GetTextExtentPoint32W.argtypes = [wintypes.HDC, wintypes.LPCWSTR, ctypes.c_int,
                                       ctypes.POINTER(wintypes.SIZE)]


class TEXTMETRICW(ctypes.Structure):
    _fields_ = [("tmHeight", wintypes.LONG), ("tmAscent", wintypes.LONG),
                ("tmDescent", wintypes.LONG), ("tmInternalLeading", wintypes.LONG),
                ("tmExternalLeading", wintypes.LONG), ("tmAveCharWidth", wintypes.LONG),
                ("tmMaxCharWidth", wintypes.LONG), ("tmWeight", wintypes.LONG),
                ("tmOverhang", wintypes.LONG), ("tmDigitizedAspectX", wintypes.LONG),
                ("tmDigitizedAspectY", wintypes.LONG), ("tmFirstChar", wintypes.WCHAR),
                ("tmLastChar", wintypes.WCHAR), ("tmDefaultChar", wintypes.WCHAR),
                ("tmBreakChar", wintypes.WCHAR), ("tmItalic", ctypes.c_byte),
                ("tmUnderlined", ctypes.c_byte), ("tmStruckOut", ctypes.c_byte),
                ("tmPitchAndFamily", ctypes.c_byte), ("tmCharSet", ctypes.c_byte)]


class BITMAPINFOHEADER(ctypes.Structure):
    _fields_ = [("biSize", wintypes.DWORD), ("biWidth", wintypes.LONG),
                ("biHeight", wintypes.LONG), ("biPlanes", wintypes.WORD),
                ("biBitCount", wintypes.WORD), ("biCompression", wintypes.DWORD),
                ("biSizeImage", wintypes.DWORD), ("biXPelsPerMeter", wintypes.LONG),
                ("biYPelsPerMeter", wintypes.LONG), ("biClrUsed", wintypes.DWORD),
                ("biClrImportant", wintypes.DWORD)]


_gdi.GetTextMetricsW.argtypes = [wintypes.HDC, ctypes.POINTER(TEXTMETRICW)]
_gdi.CreateDIBSection.restype = wintypes.HBITMAP
_gdi.CreateDIBSection.argtypes = [wintypes.HDC, ctypes.POINTER(BITMAPINFOHEADER),
                                  wintypes.UINT, ctypes.POINTER(ctypes.c_void_p),
                                  wintypes.HANDLE, wintypes.DWORD]


class GdiFont:
    """Police Windows à une taille en pixels (hauteur des cellules), sans lissage."""

    def __init__(self, face, height, bold=False):
        self.face, self.height, self.bold = face, height, bold
        self._dc = _gdi.CreateCompatibleDC(None)
        self._font = _gdi.CreateFontW(-height, 0, 0, 0, FW_BOLD if bold else FW_NORMAL,
                                      0, 0, 0, 1, 0, 0, NONANTIALIASED_QUALITY, 0, face)
        _gdi.SelectObject(self._dc, self._font)
        tm = TEXTMETRICW()
        _gdi.GetTextMetricsW(self._dc, ctypes.byref(tm))
        self.ascent, self.descent = tm.tmAscent, tm.tmDescent
        self.cell = tm.tmHeight

    def textlength(self, s):
        if not s:
            return 0
        size = wintypes.SIZE()
        _gdi.GetTextExtentPoint32W(self._dc, s, len(s), ctypes.byref(size))
        return size.cx

    @lru_cache(maxsize=512)
    def mask(self, s):
        """Masque "1" du texte (largeur du texte × hauteur de la cellule), avec une marge à
        droite : certains glyphes (°, italiques) dépassent un peu de leur avance."""
        w = max(1, self.textlength(s)) + max(2, self.cell // 4)
        h = self.cell
        bmi = BITMAPINFOHEADER(ctypes.sizeof(BITMAPINFOHEADER), w, -h, 1, 32, 0, 0, 0, 0, 0, 0)
        bits = ctypes.c_void_p()
        dib = _gdi.CreateDIBSection(self._dc, ctypes.byref(bmi), DIB_RGB_COLORS,
                                    ctypes.byref(bits), None, 0)
        old = _gdi.SelectObject(self._dc, dib)
        try:
            ctypes.memset(bits, 0, w * h * 4)
            _gdi.SetBkMode(self._dc, TRANSPARENT)
            _gdi.SetTextColor(self._dc, 0x00FFFFFF)
            _gdi.TextOutW(self._dc, 0, 0, s, len(s))
            raw = ctypes.string_at(bits, w * h * 4)
        finally:
            _gdi.SelectObject(self._dc, old)
            _gdi.DeleteObject(dib)
        img = Image.frombuffer("RGBX", (w, h), raw, "raw", "BGRX", 0, 1).convert("L")
        return img.point(lambda v: 255 if v >= 128 else 0).convert("1")

    def draw(self, img, x, y, s, fill=1):
        """Texte posé avec son coin haut gauche en (x, y)."""
        if not s:
            return
        m = self.mask(s)
        img.paste(fill, (int(x), int(y)), m)
