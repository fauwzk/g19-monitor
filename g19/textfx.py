"""Caractères absents de la police : émojis (en couleur, police Segoe UI Emoji) et symboles
(Segoe UI Symbol) pris dans une police de secours, caractère par caractère. S'installe sur
ImageDraw (text et textlength), donc vaut pour tout le dessin de l'appli sans toucher aux pages.

Sans moteur de mise en forme (raqm), les séquences composées d'émojis ne se combinent pas : on
les simplifie (👍🏽 → 👍, 👨‍👩‍👧 → 👨, sélecteurs de variante retirés)."""
from functools import lru_cache

from PIL import ImageDraw, ImageFont

EMOJI_FONT = r"C:\Windows\Fonts\seguiemj.ttf"
SYMBOL_FONT = r"C:\Windows\Fonts\seguisym.ttf"
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


@lru_cache(maxsize=64)
def _fallback(kind, size):
    try:
        if kind == "emoji":
            return ImageFont.truetype(EMOJI_FONT, max(6, round(size * EMOJI_SCALE)))
        return ImageFont.truetype(SYMBOL_FONT, size)
    except OSError:
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
            kind = "main"             # nulle part : la police principale dessine son carré
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


def _font_of(kind, font):
    return font if kind == "main" else (_fallback(kind, font.size) or font)


def textlength(self, text, font=None, *args, **kwargs):
    runs = _split(text, font) if font is not None else None
    if runs is None:
        return _orig_length(self, text, font, *args, **kwargs)
    return sum(_orig_length(self, part, _font_of(kind, font)) for part, kind in runs)


def text(self, xy, text, fill=None, font=None, anchor=None, *args, **kwargs):
    runs = _split(text, font) if font is not None else None
    if runs is None:
        return _orig_text(self, xy, text, fill, font, anchor, *args, **kwargs)
    anchor = anchor or "la"
    widths = [_orig_length(self, part, _font_of(kind, font)) for part, kind in runs]
    x, y = xy
    x -= {"l": 0, "m": sum(widths) / 2, "r": sum(widths)}.get(anchor[0], 0)
    # tous les morceaux sur la ligne de base du texte principal (les polices de secours ont
    # d'autres hauteurs : alignés sur leur haut ou leur milieu, ils sautilleraient)
    y += _baseline_offset(font, anchor[1])
    for (part, kind), w in zip(runs, widths):
        f = _font_of(kind, font)
        extra = dict(kwargs)
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
