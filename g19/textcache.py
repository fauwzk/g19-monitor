"""Cache des textes déjà dessinés.

FreeType refait tout le travail (contours, hinting) à chaque texte, à chaque image : sous
Linux, avec Noto Sans, un court libellé coûte 2 à 3 ms, et une page en a une vingtaine. Or
d'une image à l'autre, presque tous les textes sont les mêmes (titres, étiquettes, valeurs qui
ne bougent pas). Le masque calculé pour (police, texte, position au quart de pixel près…) est
gardé et resservi : seul un texte nouveau coûte. Installé sur FreeTypeFont.getmask2, ce que
ImageDraw.text appelle, donc valable pour tout le dessin sans toucher aux pages."""
from PIL import ImageFont

QUANT = 4                 # position sous-pixel retenue au 1/4 de pixel
LIMIT = 6000              # masques gardés (vidé d'un coup au-delà)
_orig = ImageFont.FreeTypeFont.getmask2
_cache = {}


def _getmask2(self, text, mode="", direction=None, features=None, language=None,
              stroke_width=0, anchor=None, ink=0, start=None, *args, **kwargs):
    if args or not isinstance(text, str):
        return _orig(self, text, mode, direction, features, language, stroke_width, anchor,
                     ink, start, *args, **kwargs)
    if start:
        start = (round(start[0] * QUANT) / QUANT, round(start[1] * QUANT) / QUANT)
    key = (self, text, mode, direction, tuple(features) if features else None, language,
           stroke_width, anchor, ink, start, tuple(sorted(kwargs.items())) if kwargs else ())
    hit = _cache.get(key)
    if hit is None:
        hit = _orig(self, text, mode, direction, features, language, stroke_width, anchor,
                    ink, start, **kwargs)
        if len(_cache) >= LIMIT:
            _cache.clear()
        _cache[key] = hit
    return hit


def install():
    if ImageFont.FreeTypeFont.getmask2 is not _getmask2:
        ImageFont.FreeTypeFont.getmask2 = _getmask2
