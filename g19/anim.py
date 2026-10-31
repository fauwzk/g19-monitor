"""Transitions entre écrans du G19 : animation au choix d'une page à l'autre (◄ ►), fondu
enchaîné à l'ouverture ou à la fermeture d'un menu, du récapitulatif, de l'horloge…

Pour les styles qui balaient l'écran, la barre du haut reste fixe : elle change sur place."""
from PIL import Image, ImageDraw, ImageEnhance

HEADER = 25              # px de la barre du haut
SPEEDS = {"fast": 0.15, "normal": 0.24, "slow": 0.38}   # durée (s)
SPEED_LABELS = {"fast": "rapide", "normal": "normale", "slow": "lente"}
WAKE = 0.5               # s : apparition au démarrage et au réveil


def _ease(k):
    return 1 - (1 - k) ** 3          # départ vif, arrivée amortie


def _keep_header(out, new):
    out.paste(new.crop((0, 0, new.width, HEADER)), (0, 0))
    return out


def slide(old, new, e, d):
    """La nouvelle page pousse l'ancienne (d = 1 : arrive par la droite)."""
    w = new.width
    out = Image.new("RGB", new.size)
    out.paste(old, (-d * int(round(e * w)), 0))
    out.paste(new, (d * int(round((1 - e) * w)), 0))
    return _keep_header(out, new)


def fade(old, new, e, d):
    return Image.blend(old, new, e)


def zoom(old, new, e, d):
    """La nouvelle page grandit depuis le centre en apparaissant, l'ancienne s'assombrit."""
    w, h = new.size
    s = 0.82 + 0.18 * e
    small = new.resize((max(1, int(w * s)), max(1, int(h * s))), Image.BILINEAR)
    back = ImageEnhance.Brightness(old).enhance(1 - 0.6 * e)
    layer = back.copy()
    layer.paste(small, ((w - small.width) // 2, (h - small.height) // 2))
    return Image.blend(back, layer, min(1.0, e * 1.6))


def wipe(old, new, e, d):
    """Volet : la nouvelle page découvre l'ancienne, avec un liseré qui balaie l'écran."""
    w, h = new.size
    x = int(round(e * w))
    out = old.copy()
    if d >= 0:
        out.paste(new.crop((w - x, 0, w, h)), (w - x, 0))
        edge = w - x
    else:
        out.paste(new.crop((0, 0, x, h)), (0, 0))
        edge = x
    if 0 < x < w:
        ImageDraw.Draw(out).line((edge, HEADER, edge, h), fill=(255, 255, 255), width=2)
    return _keep_header(out, new)


def cube(old, new, e, d):
    """Cube : l'ancienne face s'écrase d'un côté pendant que la nouvelle s'ouvre de l'autre."""
    w, h = new.size
    nw = max(1, int(round(e * w)))
    ow = max(1, w - nw)
    a = ImageEnhance.Brightness(old.resize((ow, h), Image.BILINEAR)).enhance(1 - 0.5 * e)
    b = ImageEnhance.Brightness(new.resize((nw, h), Image.BILINEAR)).enhance(0.5 + 0.5 * e)
    out = Image.new("RGB", new.size)
    if d >= 0:
        out.paste(a, (0, 0))
        out.paste(b, (ow, 0))
    else:
        out.paste(b, (0, 0))
        out.paste(a, (nw, 0))
    return _keep_header(out, new)


def blinds(old, new, e, d):
    """Stores : des bandes verticales s'ouvrent les unes après les autres."""
    w, h = new.size
    n = 8
    strip = w / n
    mask = Image.new("L", new.size, 0)
    md = ImageDraw.Draw(mask)
    for i in range(n):
        k = i if d >= 0 else n - 1 - i
        local = min(1.0, max(0.0, e * 1.6 - k * 0.6 / n))   # léger décalage d'une bande à l'autre
        x0 = i * strip
        md.rectangle((x0, 0, x0 + strip * local, h), fill=255)
    out = old.copy()
    out.paste(new, (0, 0), mask)
    return _keep_header(out, new)


STYLES = {"slide": ("glisser", slide), "fade": ("fondu", fade), "zoom": ("zoom", zoom),
          "wipe": ("volet", wipe), "cube": ("cube", cube), "blinds": ("stores", blinds),
          "none": ("aucune", None)}


class Transitions:
    def __init__(self):
        self.key = None          # écran affiché : (mode, page)
        self.prev = None         # sa dernière image (sans transition)
        self.current = None      # (ancienne image, début, fonction, sens, durée)

    def frame(self, key, img, now, order=(), enabled=True, style="slide", speed="normal"):
        """Image à afficher pour l'écran `key` dont la nouvelle image est `img` ; `order` :
        ordre des pages, pour le sens de l'animation ; `style` : celle des changements de
        page (les autres écrans arrivent en fondu)."""
        img = img.convert("RGB") if img.mode != "RGB" else img
        if not enabled:
            self.current = None
        elif self.key is None:
            # tout premier écran (démarrage, relance) : il apparaît depuis le noir
            self.current = (Image.new("RGB", img.size), now, fade, 0, WAKE)
        elif style == "none" and key[0] == self.key[0] == "page" and key[1] != self.key[1]:
            self.current = None       # changement de page sans animation
        elif self.key is not None and key != self.key and self.prev is not None \
                and self.prev.size == img.size:
            fn, direction = fade, 0
            # autre page : le style choisi ; même page, autre vue (OK) : fondu
            if key[0] == self.key[0] == "page" and key[1] != self.key[1] \
                    and key[1] in order and self.key[1] in order:
                i, j, n = order.index(self.key[1]), order.index(key[1]), len(order)
                fn = STYLES.get(style, STYLES["slide"])[1] or fade
                if (j - i) % n == 1:
                    direction = 1
                elif (i - j) % n == 1:
                    direction = -1
                else:
                    direction = 1 if j > i else -1
            duration = SPEEDS.get(speed, SPEEDS["normal"])
            if self.key[0] == "idle":
                duration = WAKE           # réveil après l'horloge de repos : plus doux
            self.current = (self.prev, now, fn, direction, duration)
        self.key, self.prev = key, img
        if not self.current:
            return img
        old, start, fn, direction, duration = self.current
        k = (now - start) / duration
        if k >= 1 or k < 0:
            self.current = None
            return img
        return fn(old, img, _ease(k), direction)
