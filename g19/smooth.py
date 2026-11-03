"""Formes lissées (anticrénelage) pour l'écran du G19.

Pillow dessine arcs, cercles, coins arrondis et traits en biais sans lissage : sur 320×240,
les jauges et les avatars ont des escaliers. `Draw(img)` rend le même outil que
ImageDraw.Draw, mais chaque forme est d'abord tracée dans un masque AA fois plus grand,
réduit (moyenne des sous-pixels), puis posé dans sa couleur. Les masques sont gardés en
cache : un panneau qui ne bouge pas ne coûte rien d'une image à l'autre.

Le texte (déjà lissé par FreeType), les rectangles droits et les traits horizontaux ou
verticaux passent tels quels. `enabled` False (réglage, thème Pixel) : dessin d'origine."""
import math

from PIL import Image, ImageDraw

AA = 4                   # sous-pixels par pixel, dans chaque sens
CACHE_MAX = 3000
enabled = True
_cache = {}


def _flat(xy):
    """[(x, y), …], [x, y, …] ou (x0, y0, x1, y1) → liste plate de nombres."""
    out = []
    for v in xy:
        if isinstance(v, (tuple, list)):
            out.extend(v)
        else:
            out.append(v)
    return out


def _ink(fill, mode):
    """Couleur pour Image.paste : celle d'ImageDraw (l'alpha d'une couleur RGBA ne compte
    que sur une image RGBA, comme avec ImageDraw)."""
    if isinstance(fill, (tuple, list)):
        fill = tuple(int(v) for v in fill)
        if mode == "RGB" and len(fill) == 4:
            fill = fill[:3]
        elif mode == "RGBA" and len(fill) == 3:
            fill = fill + (255,)
    return fill


class SmoothDraw(ImageDraw.ImageDraw):
    def _smooth(self, key, bounds, pad, paint, color):
        """Pose `color` à travers un masque lissé. `bounds` : (x0, y0, x1, y1) de la forme
        en pixels ; `paint(draw, sx, sy)` la trace dans le masque agrandi, où sx / sy
        convertissent une coordonnée de l'image."""
        x0, y0, x1, y1 = bounds
        ox, oy = math.floor(x0 - pad), math.floor(y0 - pad)
        w, h = math.ceil(x1 + pad) - ox + 1, math.ceil(y1 + pad) - oy + 1
        if w <= 0 or h <= 0 or w > 4 * self.im.size[0] or h > 4 * self.im.size[1]:
            return False
        # même forme au même endroit à 1/AA de pixel près : même masque
        ck = (key, w, h, round((x0 - ox) * AA), round((y0 - oy) * AA))
        mask = _cache.get(ck)
        if mask is None:
            big = Image.new("L", (w * AA, h * AA), 0)
            paint(ImageDraw.Draw(big), lambda x: (x - ox) * AA, lambda y: (y - oy) * AA)
            mask = big.reduce(AA)
            if len(_cache) >= CACHE_MAX:
                _cache.clear()
            _cache[ck] = mask
        self._image.paste(_ink(color, self._image.mode), (ox, oy), mask)
        return True

    def _ok(self):
        return enabled and self._image.mode in ("RGB", "RGBA")

    # --- formes dans une boîte : ellipse, rectangle arrondi, arc, part, corde ---

    def _boxed(self, kind, xy, fill, outline, width, extra, draw_fn):
        x0, y0, x1, y1 = _flat(xy)[:4]
        if x1 < x0 or y1 < y0:
            return
        rel = (round((x1 - x0) * AA), round((y1 - y0) * AA))

        def box(sx, sy):
            # pixel x couvre [x, x + 1) : la boîte inclusive (x0…x1) va jusqu'à x1 + 1
            return (sx(x0), sy(y0), sx(x1 + 1) - 1, sy(y1 + 1) - 1)

        if fill is not None:
            self._smooth((kind, "fill", rel, extra), (x0, y0, x1, y1), 1,
                         lambda d, sx, sy: draw_fn(d, box(sx, sy), 255, None, 0), fill)
        if outline is not None and width:
            self._smooth((kind, "line", rel, extra, width), (x0, y0, x1, y1), 1,
                         lambda d, sx, sy: draw_fn(d, box(sx, sy), None, 255, width * AA),
                         outline)

    def ellipse(self, xy, fill=None, outline=None, width=1):
        if not self._ok():
            return super().ellipse(xy, fill, outline, width)
        self._boxed("ellipse", xy, fill, outline, width, None,
                    lambda d, b, f, o, w: d.ellipse(b, fill=f, outline=o, width=w))

    def rounded_rectangle(self, xy, radius=0, fill=None, outline=None, width=1, *,
                          corners=None):
        if not self._ok() or radius < 1:
            return super().rounded_rectangle(xy, radius, fill, outline, width,
                                             corners=corners)
        x0, y0, x1, y1 = _flat(xy)[:4]
        if x1 - x0 < 1 or y1 - y0 < 1:
            return super().rounded_rectangle(xy, radius, fill, outline, width,
                                             corners=corners)
        r = min(radius, (x1 - x0 + 1) / 2, (y1 - y0 + 1) / 2)
        self._boxed("rrect", xy, fill, outline, width, (r, corners),
                    lambda d, b, f, o, w: d.rounded_rectangle(b, r * AA, fill=f, outline=o,
                                                              width=w, corners=corners))

    def arc(self, xy, start, end, fill=None, width=1):
        if not self._ok():
            return super().arc(xy, start, end, fill, width)
        if fill is None:
            return
        self._boxed("arc", xy, None, fill, width, (round(start, 1), round(end, 1)),
                    lambda d, b, f, o, w: d.arc(b, start, end, fill=o, width=w))

    def pieslice(self, xy, start, end, fill=None, outline=None, width=1):
        if not self._ok():
            return super().pieslice(xy, start, end, fill, outline, width)
        self._boxed("pie", xy, fill, outline, width, (round(start, 1), round(end, 1)),
                    lambda d, b, f, o, w: d.pieslice(b, start, end, fill=f, outline=o,
                                                     width=w))

    def chord(self, xy, start, end, fill=None, outline=None, width=1):
        if not self._ok():
            return super().chord(xy, start, end, fill, outline, width)
        self._boxed("chord", xy, fill, outline, width, (round(start, 1), round(end, 1)),
                    lambda d, b, f, o, w: d.chord(b, start, end, fill=f, outline=o, width=w))

    # --- formes à points : polygone, trait ---

    def polygon(self, xy, fill=None, outline=None, width=1):
        if not self._ok():
            return super().polygon(xy, fill, outline, width)
        v = _flat(xy)
        pts = list(zip(v[0::2], v[1::2]))
        if len(pts) < 3:
            return super().polygon(xy, fill, outline, width)
        xs, ys = [p[0] for p in pts], [p[1] for p in pts]
        bx, by = min(xs), min(ys)
        rel = tuple((round((x - bx) * AA), round((y - by) * AA)) for x, y in pts)

        def pp(sx, sy):
            # sommets au centre des pixels, comme ImageDraw
            return [(sx(x + 0.5), sy(y + 0.5)) for x, y in pts]

        bounds = (bx, by, max(xs), max(ys))
        if fill is not None:
            self._smooth(("poly", "fill", rel), bounds, 1,
                         lambda d, sx, sy: d.polygon(pp(sx, sy), fill=255), fill)
        if outline is not None and width:
            self._smooth(("poly", "line", rel, width), bounds, width,
                         lambda d, sx, sy: d.polygon(pp(sx, sy), outline=255,
                                                     width=width * AA), outline)

    def line(self, xy, fill=None, width=1, joint=None):
        # épaisseur 0 : 1 px, comme Pillow ≤ 11 (Pillow 12 ne trace plus rien à 0)
        width = max(1, width or 0)
        if not self._ok() or fill is None:
            return super().line(xy, fill, width, joint)
        v = _flat(xy)
        pts = list(zip(v[0::2], v[1::2]))
        # traits droits (séparateurs, graduations) : déjà nets, on ne touche pas
        if len(pts) < 2 or all(a[0] == b[0] or a[1] == b[1]
                               for a, b in zip(pts, pts[1:])):
            return super().line(xy, fill, width, joint)
        wd = max(1, width)
        xs, ys = [p[0] for p in pts], [p[1] for p in pts]
        bx, by = min(xs), min(ys)
        rel = tuple((round((x - bx) * AA), round((y - by) * AA)) for x, y in pts)

        def paint(d, sx, sy):
            sp = [(sx(x + 0.5), sy(y + 0.5)) for x, y in pts]
            d.line(sp, fill=255, width=wd * AA, joint=joint or ("curve" if wd > 1 else None))
            if wd > 1:            # bouts arrondis, comme un trait de stylo
                r = wd * AA / 2
                for x, y in (sp[0], sp[-1]):
                    d.ellipse((x - r, y - r, x + r, y + r), fill=255)

        self._smooth(("line", rel, wd, joint), (bx, by, max(xs), max(ys)), wd, paint, fill)


def Draw(img):
    """Comme ImageDraw.Draw, formes lissées en plus (images RGB / RGBA)."""
    return SmoothDraw(img)
