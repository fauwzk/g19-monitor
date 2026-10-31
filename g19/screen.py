"""Réglages de l'écran du G19 appliqués à chaque image avant l'envoi : luminosité, contraste,
gamma (relève les tons sombres, que le LCD écrase), saturation, netteté. Et une mire pour les
régler à l'œil directement sur le clavier."""

from PIL import Image, ImageDraw, ImageEnhance, ImageFilter

from .lcd import H, W

try:
    import numpy as np
except ImportError:
    np = None

# l'écran du G19 est en 16 bits (5 bits rouge, 6 vert, 5 bleu) : un dégradé lisse et sombre
# (pochette floutée, fond d'écran) y tombe en paliers visibles. Un tramage ordonné 4×4 répartit
# les teintes intermédiaires entre les deux niveaux voisins : les bandes disparaissent.
_BAYER = None
_STEP = (8.0, 4.0, 8.0)


def dither(img, cfg):
    """Image prête pour l'écran 16 bits, tramée (réglage screen_dither)."""
    global _BAYER
    if np is None or not cfg.get("screen_dither", True):
        return img
    if _BAYER is None:
        b = np.array([[0, 8, 2, 10], [12, 4, 14, 6], [3, 11, 1, 9], [15, 7, 13, 5]],
                     dtype=np.float32) / 16.0
        _BAYER = np.tile(b, (H // 4 + 1, W // 4 + 1))[:H, :W, None]
    a = np.asarray(img.convert("RGB"), dtype=np.float32)
    if a.shape[:2] != _BAYER.shape[:2]:
        return img
    step = np.array(_STEP, dtype=np.float32)
    q = np.floor(a / step + _BAYER) * step
    return Image.fromarray(np.clip(q, 0, 255).astype(np.uint8))

DEFAULTS = {"screen_brightness": 100, "screen_contrast": 100, "screen_gamma": 100,
            "screen_saturation": 100, "screen_sharpen": False, "screen_dither": True}
PATTERN_SECONDS = 20

_lut = {"key": None, "table": None}


def _table(brightness, contrast, gamma):
    """Une table par canal combinant gamma, contraste (autour du gris moyen) et luminosité."""
    key = (brightness, contrast, gamma)
    if _lut["key"] != key:
        g = 100 / max(gamma, 10)            # gamma > 100 : tons sombres relevés
        c, b = contrast / 100, brightness / 100
        out = []
        for v in range(256):
            x = (v / 255) ** g
            x = (x - 0.5) * c + 0.5
            out.append(max(0, min(255, round(x * b * 255))))
        _lut["key"], _lut["table"] = key, out * 3
    return _lut["table"]


def adjust(img, cfg):
    b = cfg.get("screen_brightness", 100)
    c = cfg.get("screen_contrast", 100)
    g = cfg.get("screen_gamma", 100)
    sat = cfg.get("screen_saturation", 100)
    if (b, c, g) != (100, 100, 100):
        img = img.point(_table(b, c, g))
    if sat != 100:
        img = ImageEnhance.Color(img).enhance(sat / 100)
    if cfg.get("screen_sharpen"):
        img = img.filter(ImageFilter.UnsharpMask(radius=1, percent=60, threshold=2))
    return img


def pattern(t, shown_at):
    """Mire : dégradé de gris en 16 marches (les marches sombres doivent rester distinctes),
    couleurs primaires et secondaires, textes de 8 à 16 px, damier fin pour la netteté."""
    img = Image.new("RGB", (W, H), (0, 0, 0))
    d = ImageDraw.Draw(img)
    from .render import font
    d.text((8, 6), "Mire de réglage de l'écran", font=font(13, True), fill=(255, 255, 255))
    left = max(0, PATTERN_SECONDS - (t - shown_at))
    d.text((W - 8, 8), f"{left:.0f} s · une touche pour fermer", font=font(9),
           fill=(200, 200, 200), anchor="ra")
    # marches de gris
    for i in range(16):
        v = round(i * 255 / 15)
        x0 = 8 + i * 19
        d.rectangle((x0, 30, x0 + 18, 62), fill=(v, v, v))
    d.text((8, 66), "les 4 premières marches doivent se distinguer du noir", font=font(9),
           fill=(190, 190, 190))
    # couleurs
    colors = [(255, 0, 0), (255, 128, 0), (255, 255, 0), (0, 255, 0), (0, 255, 255),
              (0, 128, 255), (0, 0, 255), (255, 0, 255), (255, 255, 255)]
    for i, col in enumerate(colors):
        x0 = 8 + i * 34
        d.rectangle((x0, 82, x0 + 32, 108), fill=col)
        d.rectangle((x0, 110, x0 + 32, 118), fill=tuple(v // 4 for v in col))
    # textes
    y = 128
    for size in (8, 9, 10, 12, 14, 16):
        d.text((8, y), f"{size} px · CPU 64 °C · 1 234 tr/min",
               font=font(size), fill=(230, 230, 230))
        y += size + 6
    # damier fin (netteté)
    for yy in range(200, 236, 2):
        for xx in range(230, 312, 2):
            if (xx + yy) % 4 == 0:
                d.point((xx, yy), fill=(255, 255, 255))
    d.rectangle((228, 198, 313, 237), outline=(120, 120, 120))
    return img
