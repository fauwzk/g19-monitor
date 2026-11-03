"""Fond d'écran Windows (ou du bureau Linux : KDE, GNOME), recadré à la taille du G19 et flouté,
pour le fond des pages (réglage « fond d'écran » ou thème Aero). Relu quand le fond change
(diaporama compris)."""
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


KDE_CONFIG = Path.home() / ".config" / "plasma-org.kde.plasma.desktop-appletsrc"


def _image_file(value):
    """Fichier image d'un réglage de bureau : chemin, file://…, ou dossier de thème KDE
    (contents/images/*, la plus grande)."""
    value = (value or "").strip().strip("'\"")
    if value.startswith("file://"):
        from urllib.parse import unquote
        value = unquote(value[7:])
    p = Path(value) if value else None
    if p and p.is_dir():
        images = [f for f in (p / "contents" / "images").glob("*")
                  if f.suffix.lower() in (".png", ".jpg", ".jpeg", ".webp")]
        p = max(images, key=lambda f: f.stat().st_size) if images else None
    return p if p and p.is_file() else None


def _linux_path():
    """Fond d'écran sous Linux : KDE Plasma (sa config), sinon GNOME (gsettings)."""
    try:
        section = ""
        for line in KDE_CONFIG.read_text("utf-8", "replace").splitlines():
            if line.startswith("["):
                section = line
            elif line.startswith("Image=") and "[org.kde.image][General]" in section:
                p = _image_file(line[6:])
                if p:
                    return p
    except OSError:
        pass
    import subprocess
    for key in ("picture-uri-dark", "picture-uri"):
        try:
            out = subprocess.run(["gsettings", "get", "org.gnome.desktop.background", key],
                                 capture_output=True, text=True, timeout=3).stdout
        except (OSError, subprocess.SubprocessError):
            break
        p = _image_file(out)
        if p:
            return p
    return None


def _path():
    if os.name != "nt":
        return _linux_path()
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
