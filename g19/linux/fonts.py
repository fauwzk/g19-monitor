"""Polices sous Linux : chaque police de Windows demandée par l'appli (segoeui.ttf, tahoma.ttf…)
trouve son équivalent libre via fontconfig (fc-match), et les icônes Segoe (codes privés
U+E700…) sont remplacées par des symboles Unicode proches."""
import subprocess
from functools import lru_cache

from PIL import ImageFont

# police Windows → motif fontconfig de son équivalent libre
WIN_TO_FC = {
    "segoeui.ttf": "Noto Sans", "segoeuib.ttf": "Noto Sans:bold",
    "seguisb.ttf": "Noto Sans:semibold",
    "tahoma.ttf": "DejaVu Sans", "tahomabd.ttf": "DejaVu Sans:bold",
    "times.ttf": "Liberation Serif", "timesbd.ttf": "Liberation Serif:bold",
    "trebuc.ttf": "DejaVu Sans", "trebucbd.ttf": "DejaVu Sans:bold",
    "framd.ttf": "DejaVu Sans Condensed:bold",
    "CascadiaMono.ttf": "DejaVu Sans Mono",
    "seguisym.ttf": "DejaVu Sans",
    "seguiemj.ttf": "Noto Emoji",
    "YuGothM.ttc": "Noto Sans CJK JP", "YuGothB.ttc": "Noto Sans CJK JP:bold",
    "msyh.ttc": "Noto Sans CJK SC", "msyhbd.ttc": "Noto Sans CJK SC:bold",
    "msjh.ttc": "Noto Sans CJK TC", "msjhbd.ttc": "Noto Sans CJK TC:bold",
    "malgun.ttf": "Noto Sans CJK KR", "malgunbd.ttf": "Noto Sans CJK KR:bold",
    "Nirmala.ttc": "Noto Sans Devanagari", "LeelawUI.ttf": "Noto Sans Thai",
    "ebrima.ttf": "Noto Sans Ethiopic", "ebrimabd.ttf": "Noto Sans Ethiopic:bold",
    "seguihis.ttf": "Noto Sans Runic", "cambria.ttc": "Noto Sans Math",
    "cambriab.ttf": "Noto Sans Math",
}


@lru_cache(maxsize=None)
def path(win_name):
    """Fichier de la police libre qui remplace `win_name`, None si fontconfig n'en a pas.
    fc-match renvoie toujours quelque chose : on vérifie que c'est bien la famille voulue."""
    pattern = WIN_TO_FC.get(win_name)
    if not pattern:
        return None
    try:
        out = subprocess.run(["fc-match", "-f", "%{file}\n%{family}", pattern],
                             capture_output=True, text=True, timeout=5).stdout.split("\n")
    except (OSError, subprocess.SubprocessError):
        return None
    if len(out) < 2 or not out[0]:
        return None
    wanted = pattern.split(":")[0].lower()
    return out[0] if wanted in out[1].lower() else None


# icônes Segoe Fluent / MDL2 → symboles Unicode, du plus ressemblant au plus sûr
ICONS = {
    "": "▦",        # calendrier
    "": "⌂",        # maison
    "": "☼",        # lampe
    "": "⏻◉",       # interrupteur
    "": "✦",        # scène
    "": "▶",        # script (lancer)
    "": "❋✣",       # ventilateur
    "": "◉",        # caméra (réunion en ligne)
    "": "🕭♪",       # cloche
    "": "🔒⊠",       # cadenas
    "": "✉",        # message
    "": "⟲↺",       # historique
    "": "▭",        # écran
    "": "⧈▣",       # conteneur
    "": "☺",        # personnes
    "": "▮",        # batterie
    "": "⛽⛟",       # voiture / carburant
    "": "◈",        # manette
    "": "☾",        # lune
    "": "◁", "": "◀", "": "◀", "": "◀",   # haut-parleur
    "": "✕",        # muet
    "": "●",        # micro
    "": "♪♫",       # musique
}
ICON_FONTS = ("DejaVu Sans", "Noto Sans Symbols 2", "Noto Sans Symbols", "Noto Sans")


@lru_cache(maxsize=None)
def _font_file(family):
    try:
        out = subprocess.run(["fc-match", "-f", "%{file}\n%{family}", family],
                             capture_output=True, text=True, timeout=5).stdout.split("\n")
    except (OSError, subprocess.SubprocessError):
        return None
    return out[0] if len(out) > 1 and family.lower() in out[1].lower() else None


@lru_cache(maxsize=None)
def _notdef(file):
    """Dessin du carré « caractère absent » de la police (sans fontTools : Pillow seul)."""
    f = ImageFont.truetype(file, 24)
    return f.getmask("\U0010FFFD").tobytes()


@lru_cache(maxsize=None)
def _has(file, ch):
    try:
        mask = ImageFont.truetype(file, 24).getmask(ch)
    except OSError:
        return False
    return bool(mask.getbbox()) and mask.tobytes() != _notdef(file)


@lru_cache(maxsize=None)
def icon_glyph(glyph):
    """(caractère, fichier de police) qui remplace l'icône Segoe `glyph`."""
    for ch in ICONS.get(glyph, "") or "•":
        for family in ICON_FONTS:
            f = _font_file(family)
            if f and _has(f, ch):
                return ch, f
    return "•", _font_file("DejaVu Sans")


@lru_cache(maxsize=256)
def _icon_font(file, size):
    return ImageFont.truetype(file, size)


def icon(d, glyph, cx, cy, size, color):
    ch, f = icon_glyph(glyph)
    if not f:
        return False
    d.text((cx, cy), ch, font=_icon_font(f, max(6, round(size * 0.95))), fill=color,
           anchor="mm")
    return True
