"""Caractères absents de la police : émojis (en couleur, police Segoe UI Emoji), symboles
(Segoe UI Symbol) et autres écritures (japonais, chinois, coréen, thaï…, polices de Windows)
pris dans une police de secours, caractère par caractère. S'installe sur
ImageDraw (text et textlength), donc vaut pour tout le dessin de l'appli sans toucher aux pages.

Sans moteur de mise en forme (raqm), les séquences composées d'émojis ne se combinent pas : on
les simplifie (👍🏽 → 👍, 👨‍👩‍👧 → 👨, sélecteurs de variante retirés)."""
import os
from functools import lru_cache

from PIL import ImageDraw, ImageFont

EMOJI_FONT = r"C:\Windows\Fonts\seguiemj.ttf"
SYMBOL_FONT = r"C:\Windows\Fonts\seguisym.ttf"
FONTS_DIR = "C:\\Windows\\Fonts\\"
if os.name != "nt":           # Linux : équivalents libres (Noto, DejaVu) via fontconfig
    from .linux import fonts as _fonts
    EMOJI_FONT = _fonts.path("seguiemj.ttf") or ""
    SYMBOL_FONT = _fonts.path("seguisym.ttf") or ""
    FONTS_DIR = ""


# Linux : Noto Color Emoji n'existe qu'en une taille (109 px, images en couleur) : chaque
# émoji y est dessiné puis réduit à la taille du texte (BITMAP_EMOJI)
BITMAP_EMOJI = os.name != "nt" and "color" in EMOJI_FONT.lower()
BITMAP_SIZE = 109


@lru_cache(maxsize=1)
def _bitmap_font():
    return ImageFont.truetype(EMOJI_FONT, BITMAP_SIZE)


@lru_cache(maxsize=2048)
def _bitmap_emoji(ch, size):
    """Émoji en couleur (RGBA) à la hauteur `size` px, ou None."""
    from PIL import Image
    try:
        f = _bitmap_font()
        w = max(1, int(f.getlength(ch)))
        img = Image.new("RGBA", (w, BITMAP_SIZE + 30), (0, 0, 0, 0))
        ImageDraw.Draw(img).text((0, 0), ch, font=f, embedded_color=True)
        box = img.getbbox()
        if not box:
            return None
        img = img.crop((0, box[1], w, box[3]))
        k = size / max(1, img.height)
        return img.resize((max(1, round(img.width * k)), max(1, round(img.height * k))),
                          Image.LANCZOS)
    except (OSError, ValueError):
        return None


def _emoji_size(font):
    return max(6, round(font.size * EMOJI_SCALE))


def _script_file(name):
    """Fichier d'une police de secours (écritures non latines)."""
    return FONTS_DIR + name if os.name == "nt" else (_fonts.path(name) or "")


# autres écritures, dans l'ordre d'essai : (nom, police normale, police grasse)
SCRIPTS = (("yugothic", "YuGothM.ttc", "YuGothB.ttc"),       # japonais (kana et kanji)
           ("yahei", "msyh.ttc", "msyhbd.ttc"),              # chinois simplifié
           ("jhenghei", "msjh.ttc", "msjhbd.ttc"),           # chinois traditionnel
           ("malgun", "malgun.ttf", "malgunbd.ttf"),         # coréen
           ("nirmala", "Nirmala.ttc", "Nirmala.ttc"),        # écritures de l'Inde
           ("leelawadee", "LeelawUI.ttf", "LeelawUI.ttf"),   # thaï, lao, khmer
           ("ebrima", "ebrima.ttf", "ebrimabd.ttf"),         # écritures africaines
           ("historic", "seguihis.ttf", "seguihis.ttf"),     # runes, gotique…
           ("cambria", "cambria.ttc", "cambriab.ttf"))       # lettres mathématiques 𝓐 𝕏
EMOJI_SCALE = 0.95          # les émojis sont plus larges que le texte à taille égale
ZWJ = 0x200D
SKIP = {0xFE0E, 0xFE0F, 0x20E3} | set(range(0x1F3FB, 0x1F400))   # variantes, teintes de peau

_orig_text = ImageDraw.ImageDraw.text
_orig_length = ImageDraw.ImageDraw.textlength


@lru_cache(maxsize=None)
def _cmap(path):
    """Points de code couverts par une police (None si illisible : on suppose tout couvert)."""
    try:
        from fontTools.ttLib import TTCollection, TTFont
        font = TTCollection(path).fonts[0] if path.lower().endswith(".ttc") else \
            TTFont(path, lazy=True)
        return frozenset(font.getBestCmap())
    except Exception:
        return None


@lru_cache(maxsize=128)
def _fallback(kind, size, bold=False):
    try:
        if kind == "emoji":
            return ImageFont.truetype(EMOJI_FONT, max(6, round(size * EMOJI_SCALE)))
        if kind == "symbol":
            return ImageFont.truetype(SYMBOL_FONT, size)
        for name, regular, heavy in SCRIPTS:
            if name == kind:
                return ImageFont.truetype(_script_file(heavy if bold else regular), size)
    except OSError:
        pass
    return None


@lru_cache(maxsize=4096)
def _script_of(cp):
    """Police d'écriture qui a ce caractère (cmaps lues seulement au besoin), ou None."""
    for name, regular, _heavy in SCRIPTS:
        cmap = _cmap(_script_file(regular))
        if cmap and cp in cmap:
            return name
    return None


def clean(text):
    """Retire ce que l'on ne sait pas combiner (teintes, variantes, suites liées par ZWJ)."""
    out, skip_next = [], False
    for ch in text:
        cp = ord(ch)
        if skip_next:
            skip_next = False
            continue
        if cp == ZWJ:
            skip_next = True          # 👨‍👩 : on garde le premier émoji de la suite
            continue
        if cp in SKIP:
            continue
        out.append(ch)
    return "".join(out)


@lru_cache(maxsize=4096)
def _runs(text, path, size):
    """[(morceau, "main" | "emoji" | "symbol")] pour un texte non ASCII."""
    main = _cmap(path)
    emoji, symbol = _cmap(EMOJI_FONT), _cmap(SYMBOL_FONT)
    runs = []
    for ch in clean(text):
        cp = ord(ch)
        if main is None or cp in main or cp < 0x80:
            kind = "main"
        elif emoji and cp in emoji:
            kind = "emoji"
        elif symbol and cp in symbol:
            kind = "symbol"
        else:
            # autre écriture, sinon nulle part : la police principale dessine son carré
            kind = _script_of(cp) or "main"
        if runs and runs[-1][1] == kind:
            runs[-1] = (runs[-1][0] + ch, kind)
        else:
            runs.append((ch, kind))
    return tuple(runs)


def _split(text, font):
    """None quand le texte s'affiche tel quel dans `font` (cas courant, vite tranché)."""
    if not isinstance(text, str) or text.isascii() or "\n" in text:
        return None
    path = getattr(font, "path", None)
    if not isinstance(path, str):
        return None
    runs = _runs(text, path, font.size)
    if len(runs) == 1 and runs[0][1] == "main":
        return None if runs[0][0] == text else runs
    return runs


def _bold(font):
    try:
        return "bold" in font.getname()[1].lower()
    except (AttributeError, IndexError, TypeError):
        return False


def _font_of(kind, font):
    return font if kind == "main" else (_fallback(kind, font.size, _bold(font)) or font)


def _part_length(self, part, kind, font):
    if kind == "emoji" and BITMAP_EMOJI:
        return sum((e.width + 1) if (e := _bitmap_emoji(ch, _emoji_size(font))) else 0
                   for ch in part)
    return _orig_length(self, part, _font_of(kind, font))


def textlength(self, text, font=None, *args, **kwargs):
    runs = _split(text, font) if font is not None else None
    if runs is None:
        return _orig_length(self, text, font, *args, **kwargs)
    return sum(_part_length(self, part, kind, font) for part, kind in runs)


def text(self, xy, text, fill=None, font=None, anchor=None, *args, **kwargs):
    runs = _split(text, font) if font is not None else None
    if runs is None:
        return _orig_text(self, xy, text, fill, font, anchor, *args, **kwargs)
    anchor = anchor or "la"
    widths = [_part_length(self, part, kind, font) for part, kind in runs]
    x, y = xy
    x -= {"l": 0, "m": sum(widths) / 2, "r": sum(widths)}.get(anchor[0], 0)
    # tous les morceaux sur la ligne de base du texte principal (les polices de secours ont
    # d'autres hauteurs : alignés sur leur haut ou leur milieu, ils sautilleraient)
    y += _baseline_offset(font, anchor[1])
    for (part, kind), w in zip(runs, widths):
        f = _font_of(kind, font)
        extra = dict(kwargs)
        if kind == "emoji" and BITMAP_EMOJI:
            # posé sur la ligne de base, un peu sous elle comme un caractère
            size = _emoji_size(font)
            ex = x
            for ch in part:
                e = _bitmap_emoji(ch, size)
                if e is not None and self.im.mode in ("RGB", "RGBA"):
                    top = int(round(y - e.height + size * 0.12))
                    self._image.paste(e, (int(round(ex)), top), e)
                    ex += e.width + 1
            x += w
            continue
        if kind == "emoji" and self.im.mode in ("RGB", "RGBA"):
            extra["embedded_color"] = True
            mode, self.fontmode = self.fontmode, "L"   # thème Pixel : lissage coupé ailleurs
            try:
                _orig_text(self, (x, y), part, fill, f, "ls", *args, **extra)
            finally:
                self.fontmode = mode
        else:
            _orig_text(self, (x, y), part, fill, f, "ls", *args, **extra)
        x += w


@lru_cache(maxsize=256)
def _baseline_offset(font, vertical):
    """Distance entre le point d'ancrage vertical (a, m, t, b, d…) et la ligne de base."""
    try:
        return font.getbbox("Hx", anchor="l" + vertical)[3] - font.getbbox("Hx", anchor="ls")[3]
    except (ValueError, TypeError):
        return 0


def install():
    if ImageDraw.ImageDraw.text is not text:
        ImageDraw.ImageDraw.text = text
        ImageDraw.ImageDraw.textlength = textlength
