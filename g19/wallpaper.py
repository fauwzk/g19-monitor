"""Fond d'écran Windows, recadré à la taille du G19 et flouté, pour le fond des pages (réglage
« fond d'écran » ou thème Aero). Relu quand Windows change de fond (diaporama compris)."""
import ctypes
import os
import time
from pathlib import Path

from PIL import Image, ImageFilter, ImageOps

SPI_GETDESKWALLPAPER = 0x0073
CHECK_EVERY = 10          # s entre deux vérifications du fichier
TRANSCODED = Path(os.environ.get("APPDATA", "")) / "Microsoft" / "Windows" / "Themes" / \
    "TranscodedWallpaper"

_state = {"checked": 0.0, "key": None, "img": None}


def _path():
    buf = ctypes.create_unicode_buffer(520)
    if ctypes.windll.user32.SystemParametersInfoW(SPI_GETDESKWALLPAPER, len(buf), buf, 0):
        p = Path(buf.value)
        if buf.value and p.is_file():
            return p
    return TRANSCODED if TRANSCODED.is_file() else None


def image(size=(320, 240), blur=6):
    """Fond d'écran flouté à `size`, ou None (pas de fond d'écran, couleur unie…)."""
    now = time.time()
    if now - _state["checked"] < CHECK_EVERY and _state["key"] and _state["key"][2:] == (size, blur):
        return _state["img"]
    _state["checked"] = now
    p = _path()
    try:
        key = (str(p), p.stat().st_mtime, size, blur) if p else None
    except OSError:
        key = None
    if key != _state["key"]:
        _state["key"], _state["img"] = key, None
        if key:
            try:
                with Image.open(p) as im:
                    im.draft("RGB", (size[0] * 2, size[1] * 2))   # JPEG : décodage réduit, rapide
                    fitted = ImageOps.fit(im.convert("RGB"), size, Image.LANCZOS)
                _state["img"] = fitted.filter(ImageFilter.GaussianBlur(blur)) if blur else fitted
            except (OSError, ValueError):
                _state["img"] = None
    return _state["img"]
