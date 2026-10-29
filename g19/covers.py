"""Visuels des jeux hors Steam : recherche du jeu sur le store Steam (beaucoup de jeux EA,
Ubisoft… y sont), sinon l'icône haute définition de l'exe."""
import ctypes
import json
import re
import urllib.parse
import urllib.request
from ctypes import wintypes

from PIL import Image

from . import config

LOOKUP_FILE = "store_lookup.json"
SEARCH = "https://store.steampowered.com/api/storesearch/?term={}&l=english&cc=US"


def _norm(name):
    return re.sub(r"[^a-z0-9]", "", re.sub(r"[™®©]", "", name.lower()))


def store_appid(name):
    """appid Steam d'un jeu du même nom (résultat mis en cache, None si absent du store)."""
    if not name:
        return None
    cache = config.load(LOOKUP_FILE, {}) or {}
    key = _norm(name)
    if key in cache:
        return cache[key]
    appid = None
    try:
        req = urllib.request.Request(SEARCH.format(urllib.parse.quote(name)),
                                     headers={"User-Agent": "G19Monitor"})
        with urllib.request.urlopen(req, timeout=6) as r:
            items = json.loads(r.read()).get("items", [])
        for it in items:
            if _norm(it.get("name", "")) == key:
                appid = str(it["id"])
                break
    except Exception:
        return None  # réseau : on réessaiera plus tard
    cache[key] = appid
    config.save(LOOKUP_FILE, cache)
    return appid


# --- icône d'un exe ------------------------------------------------------------------------------

class BITMAPINFOHEADER(ctypes.Structure):
    _fields_ = [("biSize", wintypes.DWORD), ("biWidth", wintypes.LONG), ("biHeight", wintypes.LONG),
                ("biPlanes", wintypes.WORD), ("biBitCount", wintypes.WORD),
                ("biCompression", wintypes.DWORD), ("biSizeImage", wintypes.DWORD),
                ("biXPelsPerMeter", wintypes.LONG), ("biYPelsPerMeter", wintypes.LONG),
                ("biClrUsed", wintypes.DWORD), ("biClrImportant", wintypes.DWORD)]


_u32 = ctypes.WinDLL("user32")
_gdi = ctypes.WinDLL("gdi32")
_u32.PrivateExtractIconsW.argtypes = [wintypes.LPCWSTR, ctypes.c_int, ctypes.c_int, ctypes.c_int,
                                      ctypes.POINTER(wintypes.HICON), ctypes.POINTER(wintypes.UINT),
                                      wintypes.UINT, wintypes.UINT]
_u32.DrawIconEx.argtypes = [wintypes.HDC, ctypes.c_int, ctypes.c_int, wintypes.HICON, ctypes.c_int,
                            ctypes.c_int, wintypes.UINT, wintypes.HBRUSH, wintypes.UINT]
_u32.DestroyIcon.argtypes = [wintypes.HICON]
_gdi.CreateCompatibleDC.argtypes = [wintypes.HDC]
_gdi.CreateCompatibleDC.restype = wintypes.HDC
_gdi.CreateDIBSection.argtypes = [wintypes.HDC, ctypes.c_void_p, wintypes.UINT,
                                  ctypes.POINTER(ctypes.c_void_p), wintypes.HANDLE, wintypes.DWORD]
_gdi.CreateDIBSection.restype = wintypes.HBITMAP
_gdi.SelectObject.argtypes = [wintypes.HDC, wintypes.HGDIOBJ]
_gdi.DeleteObject.argtypes = [wintypes.HGDIOBJ]
_gdi.DeleteDC.argtypes = [wintypes.HDC]


def exe_icon(path, size=256):
    """Icône de l'exe en RGBA (None si l'exe n'en a pas)."""
    hicon, icon_id = wintypes.HICON(), wintypes.UINT()
    if _u32.PrivateExtractIconsW(path, 0, size, size, ctypes.byref(hicon), ctypes.byref(icon_id),
                                 1, 0) < 1 or not hicon:
        return None
    hdc = _gdi.CreateCompatibleDC(None)
    bmi = BITMAPINFOHEADER(ctypes.sizeof(BITMAPINFOHEADER), size, -size, 1, 32, 0)
    bits = ctypes.c_void_p()
    hbmp = _gdi.CreateDIBSection(hdc, ctypes.byref(bmi), 0, ctypes.byref(bits), None, 0)
    try:
        old = _gdi.SelectObject(hdc, hbmp)
        _u32.DrawIconEx(hdc, 0, 0, hicon, size, size, 0, None, 3)  # DI_NORMAL
        _gdi.SelectObject(hdc, old)
        data = ctypes.string_at(bits, size * size * 4)
    finally:
        _gdi.DeleteObject(hbmp)
        _gdi.DeleteDC(hdc)
        _u32.DestroyIcon(hicon)
    img = Image.frombuffer("RGBA", (size, size), data, "raw", "BGRA", 0, 1)
    if img.getchannel("A").getextrema()[1] == 0:  # icône sans canal alpha
        img.putalpha(255)
    bbox = img.getchannel("A").getbbox()
    return img.crop(bbox) if bbox else None
