"""Apparences des thèmes qui changent la forme des éléments, pas seulement les couleurs :
Aero (verre sur le fond d'écran), Cadrans (instruments à aiguille), HUD (cockpit), Tron
(vectoriel lumineux), Papier (encre et hachures) et Pixel (8 bits).

Chaque fonction reçoit les mêmes arguments que son équivalent de render.py et renvoie True
quand elle a dessiné (False : render.py dessine comme d'habitude). Les couleurs sont celles
du thème en cours, lues dans render au moment du dessin."""
import math

from PIL import Image, ImageChops, ImageDraw, ImageFilter

from . import render as R

SHAPED = ("aero", "analog", "hud", "tron", "paper", "paper_dark", "pixel", "xp", "symbian")
PAPERS = ("paper", "paper_dark")
_cache = {}


def _cached(key, make):
    hit = _cache.get(key)
    if hit is None:
        if len(_cache) > 128:
            _cache.clear()
        hit = _cache[key] = make()
    return hit


def clear():
    _cache.clear()


def _mask(w, h, r):
    def make():
        m = Image.new("L", (w, h), 0)
        ImageDraw.Draw(m).rounded_rectangle((0, 0, w - 1, h - 1), r, fill=255)
        return m
    return _cached(("mask", w, h, r), make)


# --- verre (Aero, et tout thème quand le fond d'écran est affiché) -------------------------------

def glass(d, box, r, color, alpha, shine=False, outline=None, width=1):
    """Panneau translucide : le fond (fond d'écran) reste visible au travers."""
    img = getattr(d, "_image", None)
    x0, y0, x1, y1 = (int(v) for v in box)
    w, h = x1 - x0 + 1, y1 - y0 + 1
    if img is None or w < 4 or h < 4 or img.mode not in ("RGB", "RGBA"):
        return False
    region = img.crop((x0, y0, x1 + 1, y1 + 1))
    opaque = (255,) if img.mode == "RGBA" else ()        # calque de bandeau : reste opaque
    tinted = Image.blend(region, Image.new(img.mode, (w, h), (*color[:3], *opaque)), alpha)
    if shine:   # reflet sur la moitié haute, comme une vitre bombée
        hi = Image.new(img.mode, (w, h // 2), (255, 255, 255, *opaque))
        top = tinted.crop((0, 0, w, h // 2))
        tinted.paste(Image.blend(top, hi, 0.07), (0, 0))
    img.paste(tinted, (x0, y0), _mask(w, h, r))
    edge = outline or R.mix(color, (255, 255, 255), 0.35 if shine else 0.18)
    d.rounded_rectangle(box, r, outline=edge, width=width)
    if shine and w > 2 * r + 2:
        d.line((x0 + r, y0 + 1, x1 - r, y0 + 1), fill=R.mix(color, (255, 255, 255), 0.6))
    return True


# --- fonds de page -------------------------------------------------------------------------------

def canvas(name):
    """Fond propre au thème (sans fond d'écran), ou None."""
    W, H = R.W, R.H
    if name == "symbian":
        return _cached(("canvas", name), _symbian_canvas).copy()
    if name == "tron":
        def make():
            # grille au sol en perspective sous l'horizon, lueur à l'horizon
            img = Image.new("RGB", (W, H), R.BG)
            d = ImageDraw.Draw(img)
            hz = 132
            for y in range(hz - 14, hz + 2):
                d.line((0, y, W, y), fill=R.mix(R.BG, R.ACCENT, 0.10 * (y - hz + 14) / 16))
            line = R.mix(R.BG, R.ACCENT, 0.22)
            vx = W / 2
            for k in range(-12, 13):
                d.line((vx + k * 8, hz, vx + k * 70, H), fill=line)
            y, step = hz + 4, 4
            while y < H:
                d.line((0, y, W, y), fill=line)
                step *= 1.35
                y += step
            return img
        return _cached(("canvas", name, R.BG, R.ACCENT), make).copy()
    if name == "hud":
        def make():
            img = Image.new("RGB", (W, H), R.BG)
            d = ImageDraw.Draw(img)
            dot = R.mix(R.BG, R.ACCENT, 0.12)
            for y in range(32, H, 16):           # trame de points discrète
                for x in range(8, W, 16):
                    d.point((x, y), fill=dot)
            return img
        return _cached(("canvas", name, R.BG, R.ACCENT), make).copy()
    if name in PAPERS:
        def make():
            # grain du papier : bruit fixe très léger (plus sombre, ou plus clair sur fond sombre)
            noise = Image.effect_noise((W, H), 18).convert("L")
            base = Image.new("RGB", (W, H), R.BG)
            speck = R.mix(R.BG, (0, 0, 0), 0.06) if name == "paper" else \
                R.mix(R.BG, (255, 255, 255), 0.05)
            dots = Image.new("RGB", (W, H), speck)
            return Image.composite(dots, base, noise.point(lambda v: 255 if v > 150 else 0))
        return _cached(("canvas", name, R.BG), make).copy()
    if name == "analog":
        def make():
            col = Image.new("RGB", (1, H))
            for y in range(H):
                col.putpixel((0, y), R.mix(R.mix(R.BG, (255, 255, 255), 0.04), R.BG, y / H))
            img = col.resize((W, H))
            grain = Image.effect_noise((W, H), 10).convert("L")
            dark = Image.new("RGB", (W, H), R.mix(R.BG, (0, 0, 0), 0.25))
            return Image.composite(dark, img, grain.point(lambda v: 255 if v > 160 else 0))
        return _cached(("canvas", name, R.BG), make).copy()
    if name == "aero":
        def make():
            # sans fond d'écran : dégradé bleu avec une traînée de lumière, façon Windows 7
            col = Image.new("RGB", (1, H))
            for y in range(H):
                col.putpixel((0, y), R.mix((24, 76, 130), (6, 22, 48), y / H))
            img = col.resize((W, H))
            streak = Image.new("L", (W, H), 0)
            sd = ImageDraw.Draw(streak)
            for k in range(40):
                sd.arc((-120 + k, 60 + k, 420 - k, 380 - k), 200, 330, fill=int(90 - 2 * k), width=2)
            img.paste((140, 210, 255), (0, 0), streak.filter(ImageFilter.GaussianBlur(6)))
            return img
        return _cached(("canvas", name), make).copy()
    return None


# --- bandeau du haut -----------------------------------------------------------------------------

def title_bar(d, name):
    W = R.W
    if name == "symbian":
        _symbian_title_bar(d)
        return True
    if name == "xp":
        _xp_title_bar(d)
        return True
    if name == "aero":
        glass(d, (-4, -4, W + 3, 24), 0, R.mix(R.BG, (0, 0, 0), 0.4), 0.55, shine=True,
              outline=R.mix(R.ACCENT, R.BG, 0.3))
        return True
    if name == "analog":
        for y in range(25):
            d.line((0, y, W, y), fill=R.mix(R.mix(R.PANEL, R.ACCENT, 0.18), R.PANEL, y / 24))
        d.line((0, 23, W, 23), fill=R.mix(R.ACCENT, R.BG, 0.2))
        d.line((0, 24, W, 24), fill=R.mix(R.ACCENT, (0, 0, 0), 0.5))
        return True
    if name == "hud":
        c = R.mix(R.ACCENT, R.BG, 0.45)
        d.line((0, 24, W, 24), fill=c)
        for x in range(0, W, 16):
            d.line((x, 24, x, 21 if x % 64 else 18), fill=c)
        return True
    if name == "tron":
        d.rectangle((0, 0, W, 24), fill=R.mix(R.BG, R.PANEL, 0.8))
        d.line((0, 24, W, 24), fill=R.ACCENT)
        return True
    if name in PAPERS:
        d.rectangle((0, 0, W, 24), fill=R.PANEL)
        ink = R.mix(R.TEXT, R.PANEL, 0.25)
        d.line((0, 22, W, 22), fill=ink)
        d.line((0, 24, W, 24), fill=ink)
        return True
    if name == "pixel":
        d.rectangle((0, 0, W, 24), fill=R.PANEL)
        d.rectangle((0, 23, W, 24), fill=R.ACCENT)
        for x in range(0, W, 8):                  # créneaux sous la barre
            d.rectangle((x, 25, x + 3, 26), fill=R.mix(R.ACCENT, R.BG, 0.5))
        return True
    return False


# --- panneaux ------------------------------------------------------------------------------------

def panel(d, box, r, outline, width, color, name):
    x0, y0, x1, y1 = (int(v) for v in box)
    if name == "symbian":
        _symbian_panel(d, x0, y0, x1, y1, max(4, min(r, 8)), color, outline, width)
        return True
    if name == "xp":
        d.rounded_rectangle(box, min(r, 3), fill=color, outline=outline or XP_BORDER, width=width)
        return True
    if name == "aero":
        return glass(d, box, r, R.mix(color, (0, 0, 0), 0.25), 0.5, shine=True, outline=outline,
                     width=width)
    if name == "analog":
        d.rounded_rectangle(box, r, fill=color)
        brass = R.mix(R.ACCENT, color, 0.45)
        d.rounded_rectangle(box, r, outline=outline or brass, width=width)
        d.line((x0 + r, y0 + 1, x1 - r, y0 + 1), fill=R.mix(color, (255, 255, 255), 0.08))
        if x1 - x0 >= 100 and y1 - y0 >= 60:      # vis aux coins, seulement des grands panneaux
            for sx, sy in ((x0 + 5, y0 + 5), (x1 - 5, y0 + 5), (x0 + 5, y1 - 5), (x1 - 5, y1 - 5)):
                d.ellipse((sx - 2, sy - 2, sx + 2, sy + 2), fill=brass)
                d.line((sx - 1, sy, sx + 1, sy), fill=R.mix(brass, (0, 0, 0), 0.5))
        return True
    if name == "hud":
        if color != R.PANEL:          # fond coloré demandé (ligne choisie…) : discret
            d.rectangle(box, fill=R.mix(R.BG, color, 0.5))
        c = outline or R.mix(R.ACCENT, R.BG, 0.45)
        k = max(3, min(9, (x1 - x0) // 5, (y1 - y0) // 3))
        for (ax, ay, sx, sy) in ((x0, y0, 1, 1), (x1, y0, -1, 1), (x0, y1, 1, -1), (x1, y1, -1, -1)):
            d.line((ax, ay, ax + sx * k, ay), fill=c, width=width)
            d.line((ax, ay, ax, ay + sy * k), fill=c, width=width)
        if outline:
            d.rectangle(box, outline=R.mix(outline, R.BG, 0.5))
        return True
    if name == "tron":
        d.rounded_rectangle(box, min(r, 3), fill=R.mix(R.BG, color, 0.7),
                            outline=outline or R.mix(R.ACCENT, R.BG, 0.35), width=width)
        return True
    if name in PAPERS:
        shadow = R.mix(R.TRACK, R.BG, 0.4) if name == "paper" else R.mix(R.BG, (0, 0, 0), 0.55)
        d.rectangle((x0 + 2, y0 + 2, x1 + 2, y1 + 2), fill=shadow)                     # ombre
        d.rectangle(box, fill=color, outline=outline or R.mix(R.TEXT, color, 0.45), width=width)
        return True
    if name == "pixel":
        _pixel_box(d, x0, y0, x1, y1, color, outline or R.mix(color, (255, 255, 255), 0.25))
        return True
    return False


def _pixel_box(d, x0, y0, x1, y1, fill, edge):
    """Case à coins en escalier, bordure de 2 px, comme une boîte de dialogue 8 bits."""
    if x1 - x0 < 6 or y1 - y0 < 6:
        d.rectangle((x0, y0, x1, y1), fill=fill)
        return
    d.rectangle((x0 + 2, y0, x1 - 2, y1), fill=edge)
    d.rectangle((x0, y0 + 2, x1, y1 - 2), fill=edge)
    d.rectangle((x0 + 1, y0 + 1, x1 - 1, y1 - 1), fill=edge)
    d.rectangle((x0 + 2, y0 + 2, x1 - 2, y1 - 2), fill=fill)


# --- barres --------------------------------------------------------------------------------------

def bar(d, x, y, w, h, frac, color, name):
    frac = max(0.0, min(frac, 1.0))
    x, y, w, h = int(x), int(y), int(w), int(h)
    fw = int(w * frac)
    if name == "symbian":
        _symbian_bar(d, x, y, w, h, fw, color)
        return True
    if name == "xp":
        _xp_bar(d, x, y, w, h, frac, color)
        return True
    if name == "analog":
        d.rectangle((x, y, x + w, y + h), fill=R.mix(R.TRACK, (0, 0, 0), 0.35),
                    outline=R.mix(R.ACCENT, R.PANEL, 0.5))
        if fw > 1:
            d.rectangle((x + 1, y + 1, x + fw, y + h - 1), fill=color)
        d.line((x + fw, y - 1, x + fw, y + h + 1), fill=R.mix(R.ACCENT, (255, 255, 255), 0.3))
        return True
    if name == "hud":
        d.rectangle((x, y, x + w, y + h), outline=R.mix(R.ACCENT, R.BG, 0.55))
        for sx in range(x + 2, x + max(fw, 0) - 1, 3):     # échelle de traits
            d.line((sx, y + 2, sx, y + h - 2), fill=color)
        return True
    if name == "tron":
        d.rectangle((x, y, x + w, y + h), outline=R.mix(color, R.BG, 0.55))
        if fw > 2:
            d.rectangle((x + 2, y + 2, x + fw - 2, y + h - 2), fill=color)
        return True
    if name in PAPERS:
        d.rectangle((x, y, x + w, y + h), outline=R.mix(R.TEXT, R.BG, 0.45))
        if fw > 1:   # hachures à 45°, coupées à la partie remplie
            left, right = x + 1, x + fw
            for k in range(-h, fw, 3):
                xa, ya = left + k, y + h - 1                  # bas du trait
                xb, yb = left + k + (h - 2), y + 1            # haut du trait
                if xa < left:
                    ya, xa = ya - (left - xa), left
                if xb > right:
                    yb, xb = yb + (xb - right), right
                if xa <= xb:
                    d.line((xa, ya, xb, yb), fill=color)
        return True
    if name == "pixel":
        n = max(1, (w + 1) // 5)
        lit = frac * n
        for k in range(n):
            sx = x + k * 5
            d.rectangle((sx, y, sx + 3, y + h), fill=color if k < lit else R.mix(R.TRACK, R.BG, 0.4))
        return True
    if name == "aero":
        r = h // 2
        d.rounded_rectangle((x, y, x + w, y + h), r, fill=R.mix(R.TRACK, (0, 0, 0), 0.3))
        if fw >= h:
            d.rounded_rectangle((x, y, x + fw, y + h), r, fill=color)
            if h >= 4:
                d.line((x + r, y + 1, x + fw - r, y + 1), fill=R.mix(color, (255, 255, 255), 0.55))
        elif fw > 0:
            d.ellipse((x, y, x + h, y + h), fill=color)
        return True
    return False


# --- historiques ---------------------------------------------------------------------------------

def sparkline(d, x, y, w, h, values, color, vmax, panel_color, name):
    vals = list(values)
    x, y, w, h = int(x), int(y), int(w), int(h)
    if name == "xp":
        _xp_graph(d, x, y, w, h, vals, color, vmax, bool(panel_color))
        return True
    if name == "pixel":
        if panel_color:
            d.rectangle((x, y, x + w, y + h), fill=panel_color)
        cell = 4
        cols, rows = w // cell, max(1, h // cell)
        vals = vals[-cols:]
        for i, v in enumerate(vals):
            lit = round(min(v, vmax) / vmax * rows) if vmax else 0
            cx = x + w - (len(vals) - i) * cell
            for j in range(lit):
                cy = y + h - (j + 1) * cell
                d.rectangle((cx, cy + 1, cx + cell - 2, cy + cell - 1),
                            fill=R.mix(R.dim(color, 0.6), color, j / max(1, rows - 1)))
        return True
    if name not in ("analog", "hud", "tron", "paper", "aero"):
        return False
    if name == "analog":   # bande d'enregistreur : papier ivoire quadrillé, tracé à l'encre
        paper = (232, 224, 204)
        d.rectangle((x, y, x + w, y + h), fill=paper, outline=R.mix(R.ACCENT, R.PANEL, 0.4))
        for gx in range(x + 10, x + w, 10):
            d.line((gx, y + 1, gx, y + h - 1), fill=(214, 202, 178))
        for gy in range(y + h - 6, y, -6):
            d.line((x + 1, gy, x + w - 1, gy), fill=(214, 202, 178))
        ink = R.mix(color, (0, 0, 0), 0.45)
        width = 1
    elif name == "hud":
        if panel_color:
            d.rectangle((x, y, x + w, y + h), fill=R.BG)
        grid = R.mix(R.ACCENT, R.BG, 0.2)
        for gx in range(x, x + w + 1, 8):
            for gy in range(y, y + h + 1, 6):
                d.point((gx, gy), fill=grid)
        ink, width = color, 1
    elif name == "tron":
        if panel_color:
            d.rectangle((x, y, x + w, y + h), fill=R.mix(R.BG, R.PANEL, 0.6),
                        outline=R.mix(color, R.BG, 0.6))
        ink, width = color, 2
    elif name in PAPERS:
        if panel_color:
            d.rectangle((x, y, x + w, y + h), fill=R.PANEL, outline=R.mix(R.TEXT, R.PANEL, 0.6))
        for gy in range(y + h - 8, y, -8):
            d.line((x + 1, gy, x + w - 1, gy), fill=R.mix(R.TRACK, R.PANEL, 0.4))
        ink, width = color, 1
    else:   # aero : remplissage léger, le fond reste visible
        if panel_color:
            glass(d, (x, y, x + w, y + h), 4, R.mix(R.BG, (0, 0, 0), 0.3), 0.45)
        ink, width = color, 2
    if len(vals) < 2:
        return True
    pts = [(x + i * w / (len(vals) - 1), y + h - 2 - (h - 4) * min(v, vmax) / vmax)
           for i, v in enumerate(vals)]
    if name in ("tron", "aero"):
        d.polygon([(x, y + h)] + pts + [(x + w, y + h)], fill=R.dim(color, 0.18))
    d.line(pts, fill=ink, width=width)
    if name == "hud":   # dernière valeur entre crochets
        lx, ly = pts[-1]
        d.line((lx - 4, ly - 3, lx - 4, ly + 3), fill=color)
        d.line((lx - 4, ly - 3, lx - 2, ly - 3), fill=color)
        d.line((lx - 4, ly + 3, lx - 2, ly + 3), fill=color)
    return True


# --- jauges --------------------------------------------------------------------------------------

def gauge(d, cx, cy, r, frac, color, value, unit, label, name):
    frac = max(0.0, min(frac, 1.0))
    if name == "xp":
        _xp_gauge(d, cx, cy, r, frac, color, value, unit, label)
        return True
    if name == "analog":
        return _needle(d, cx, cy, r, frac, color, value, unit, label)
    if name == "hud":
        ticks = 27
        for k in range(ticks):
            a = math.radians(135 + k * 270 / (ticks - 1))
            on = k / (ticks - 1) <= frac + 1e-6 and frac > 0
            r0 = r - (7 if k % 13 == 0 else 5)
            d.line((cx + r0 * math.cos(a), cy + r0 * math.sin(a), cx + r * math.cos(a),
                    cy + r * math.sin(a)), fill=color if on else R.mix(R.ACCENT, R.BG, 0.25),
                   width=2 if on else 1)
        d.text((cx, cy - 2), value, font=R.font(16, True), fill=R.TEXT, anchor="mm")
        d.text((cx, cy + 13), unit, font=R.font(10), fill=R.MUTED, anchor="mm")
        d.text((cx, cy + r + 6), f"[ {label} ]", font=R.font(10), fill=R.MUTED, anchor="mm")
        return True
    if name == "tron":
        box = (cx - r, cy - r, cx + r, cy + r)
        d.arc(box, 135, 405, fill=R.mix(color, R.BG, 0.7), width=1)
        inner = (cx - r + 4, cy - r + 4, cx + r - 4, cy + r - 4)
        if frac > 0.005:
            d.arc(inner, 135, 135 + 270 * frac, fill=color, width=3)
            a = math.radians(135 + 270 * frac)
            ex, ey = cx + (r - 4) * math.cos(a), cy + (r - 4) * math.sin(a)
            d.ellipse((ex - 3, ey - 3, ex + 3, ey + 3), fill=R.mix(color, (255, 255, 255), 0.5))
        d.text((cx, cy - 2), value, font=R.font(16, True), fill=R.TEXT, anchor="mm")
        d.text((cx, cy + 13), unit, font=R.font(10), fill=R.MUTED, anchor="mm")
        d.text((cx, cy + r + 4), label, font=R.font(11), fill=R.MUTED, anchor="mm")
        return True
    if name in PAPERS:
        box = (cx - r, cy - r, cx + r, cy + r)
        ink = R.mix(R.TEXT, R.BG, 0.3)
        d.arc(box, 135, 405, fill=ink, width=1)
        for k in range(11):
            a = math.radians(135 + k * 27)
            r0 = r - (5 if k % 5 == 0 else 3)
            d.line((cx + r0 * math.cos(a), cy + r0 * math.sin(a), cx + r * math.cos(a),
                    cy + r * math.sin(a)), fill=ink)
        if frac > 0.005:
            d.arc((cx - r + 6, cy - r + 6, cx + r - 6, cy + r - 6), 135, 135 + 270 * frac,
                  fill=color, width=5)
        d.text((cx, cy - 2), value, font=R.font(16, True), fill=R.TEXT, anchor="mm")
        d.text((cx, cy + 13), unit, font=R.font(10), fill=R.MUTED, anchor="mm")
        d.text((cx, cy + r + 5), label, font=R.font(11), fill=R.MUTED, anchor="mm")
        return True
    if name == "pixel":
        blocks = 16
        for k in range(blocks):
            a = math.radians(135 + k * 270 / (blocks - 1))
            bx, by = cx + (r - 3) * math.cos(a), cy + (r - 3) * math.sin(a)
            on = (k + 0.5) / blocks <= frac
            d.rectangle((int(bx) - 2, int(by) - 2, int(bx) + 2, int(by) + 2),
                        fill=color if on else R.mix(R.TRACK, R.BG, 0.4))
        d.text((cx, cy - 2), value, font=R.font(16, True), fill=R.TEXT, anchor="mm")
        d.text((cx, cy + 13), unit, font=R.font(10), fill=R.MUTED, anchor="mm")
        d.text((cx, cy + r + 4), label, font=R.font(11), fill=R.MUTED, anchor="mm")
        return True
    if name == "aero":
        box = (cx - r, cy - r, cx + r, cy + r)
        glass(d, (cx - r - 3, cy - r - 3, cx + r + 3, cy + r + 3), r + 3,
              R.mix(R.BG, (0, 0, 0), 0.35), 0.5, shine=True)
        d.arc(box, 135, 405, fill=R.mix(R.TRACK, (0, 0, 0), 0.2), width=6)
        if frac > 0.005:
            d.arc(box, 135, 135 + 270 * frac, fill=color, width=6)
        d.text((cx, cy - 2), value, font=R.font(16, True), fill=R.TEXT, anchor="mm")
        d.text((cx, cy + 13), unit, font=R.font(10), fill=R.MUTED, anchor="mm")
        d.text((cx, cy + r + 6), label, font=R.font(11), fill=R.MUTED, anchor="mm")
        return True
    return False


IVORY = (238, 230, 212)
INK = (38, 32, 26)


def _needle(d, cx, cy, r, frac, color, value, unit, label):
    """Cadran d'instrument : fond ivoire, graduations, zone rouge, aiguille et moyeu laiton."""
    rb = r + 3
    brass = R.ACCENT
    d.ellipse((cx - rb - 2, cy - rb - 2, cx + rb + 2, cy + rb + 2),
              fill=R.mix(brass, (0, 0, 0), 0.35))
    d.ellipse((cx - rb, cy - rb, cx + rb, cy + rb), fill=IVORY,
              outline=R.mix(brass, (255, 255, 255), 0.25), width=2)
    face = (cx - r + 2, cy - r + 2, cx + r - 2, cy + r - 2)
    d.arc(face, 135 + 270 * 0.85, 405, fill=(200, 60, 40), width=3)        # zone rouge
    for k in range(21):
        a = math.radians(135 + k * 270 / 20)
        major = k % 5 == 0
        r0, r1 = r - (8 if major else 5), r - 2
        d.line((cx + r0 * math.cos(a), cy + r0 * math.sin(a), cx + r1 * math.cos(a),
                cy + r1 * math.sin(a)), fill=INK, width=2 if major else 1)
    d.text((cx, cy + r * 0.42), value + (unit if len(unit) <= 2 else ""),
           font=R.font(11, True), fill=INK, anchor="mm")
    a = math.radians(135 + 270 * frac)
    tip = (cx + (r - 5) * math.cos(a), cy + (r - 5) * math.sin(a))
    tail = (cx - 5 * math.cos(a), cy - 5 * math.sin(a))
    side = (math.cos(a + math.pi / 2) * 1.6, math.sin(a + math.pi / 2) * 1.6)
    d.polygon([tip, (tail[0] + side[0], tail[1] + side[1]), (tail[0] - side[0], tail[1] - side[1])],
              fill=(176, 30, 22))
    d.ellipse((cx - 4, cy - 4, cx + 4, cy + 4), fill=brass, outline=R.mix(brass, (0, 0, 0), 0.4))
    d.text((cx, cy + rb + 9), label, font=R.font(10), fill=R.MUTED, anchor="mm")
    return True


# --- Windows XP (bleu Luna) ----------------------------------------------------------------------

XP_BORDER = (127, 157, 185)      # bord des contrôles
XP_BLUE = ((61, 149, 255), (0, 88, 238), (0, 72, 214), (0, 46, 156))


def _xp_title_bar(d):
    W = R.W
    hi, top, mid, low = XP_BLUE
    for y in range(25):
        if y < 3:
            c = R.mix(hi, top, y / 3)
        elif y < 12:
            c = R.mix(top, mid, (y - 3) / 9)
        else:
            c = R.mix(mid, (0, 60, 190), (y - 12) / 12)
        d.line((0, y, W, y), fill=c)
    d.line((0, 0, W, 0), fill=(120, 180, 255))
    d.line((0, 24, W, 24), fill=low)


def _xp_bar(d, x, y, w, h, frac, color):
    """Barre de progression XP : piste blanche bordée, blocs dégradés espacés."""
    d.rounded_rectangle((x, y, x + w, y + h), 2, fill=(255, 255, 255), outline=XP_BORDER)
    inner_h = h - 2
    if inner_h < 1:
        return
    fw = int((w - 2) * frac)
    block, gap = max(3, min(7, inner_h + 2)), 2
    bx = x + 1
    while bx + 1 < x + 1 + fw:
        bw = min(block, x + 1 + fw - bx)
        for k in range(inner_h):
            f = k / max(1, inner_h - 1)
            c = R.mix(R.mix(color, (255, 255, 255), 0.55), color, min(1.0, f * 2.2)) if f < 0.45 \
                else R.mix(color, R.mix(color, (0, 0, 0), 0.25), (f - 0.45) / 0.55)
            d.line((bx, y + 1 + k, bx + bw - 1, y + 1 + k), fill=c)
        bx += block + gap


def _xp_graph(d, x, y, w, h, values, color, vmax, with_bg):
    """Graphe du gestionnaire des tâches : fond noir, grille verte, tracé vif."""
    if with_bg:
        d.rectangle((x, y, x + w, y + h), fill=(0, 0, 0))
        for gx in range(x + 12, x + w, 12):
            d.line((gx, y, gx, y + h), fill=(0, 100, 50))
        for gy in range(y + h - 10, y, -10):
            d.line((x, gy, x + w, gy), fill=(0, 100, 50))
    vals = list(values)
    if len(vals) < 2:
        return
    line = R.mix(color, (255, 255, 255), 0.25) if with_bg else color
    pts = [(x + i * w / (len(vals) - 1), y + h - 1 - (h - 2) * min(v, vmax) / vmax)
           for i, v in enumerate(vals)]
    d.line(pts, fill=line, width=1)


def _xp_gauge(d, cx, cy, r, frac, color, value, unit, label):
    d.ellipse((cx - r - 2, cy - r - 2, cx + r + 2, cy + r + 2), fill=(255, 255, 255),
              outline=XP_BORDER)
    box = (cx - r + 3, cy - r + 3, cx + r - 3, cy + r - 3)
    d.arc(box, 135, 405, fill=(226, 230, 236), width=6)
    segs = 15
    for k in range(segs):          # blocs comme la barre de progression, sur l'arc
        if (k + 0.5) / segs > frac:
            break
        a0 = 135 + k * 270 / segs + 2
        d.arc(box, a0, a0 + 270 / segs - 4, fill=color, width=6)
    d.text((cx, cy - 2), value, font=R.font(15, True), fill=R.TEXT, anchor="mm")
    d.text((cx, cy + 12), unit, font=R.font(9), fill=R.MUTED, anchor="mm")
    d.text((cx, cy + r + 9), label, font=R.font(10), fill=R.MUTED, anchor="mm")


# --- Nokia / Symbian (S60) -----------------------------------------------------------------------

def _symbian_canvas():
    """Fond bleu nuit dégradé traversé d'une vague de lumière, comme les fonds S60."""
    W, H = R.W, R.H
    col = Image.new("RGB", (1, H))
    for y in range(H):
        col.putpixel((0, y), R.mix((10, 46, 104), (2, 10, 30), y / H))
    img = col.resize((W, H))
    wave = Image.new("L", (W, H), 0)
    wd = ImageDraw.Draw(wave)
    for k in range(28):
        y0 = 150 + k * 2
        wd.arc((-160, y0 - 140, W + 160, y0 + 140), 200, 340, fill=max(0, 70 - k * 3), width=2)
    img.paste((120, 200, 255), (0, 0), wave.filter(ImageFilter.GaussianBlur(5)))
    return img


def _symbian_title_bar(d):
    """Barre d'état bleue vernie : reflet clair en haut, liseré lumineux en bas."""
    W = R.W
    for y in range(25):
        if y < 11:
            c = R.mix((92, 168, 240), (36, 110, 206), y / 11)
        else:
            c = R.mix((22, 88, 184), (10, 50, 128), (y - 11) / 13)
        d.line((0, y, W, y), fill=c)
    d.line((0, 0, W, 0), fill=(170, 215, 255))
    d.line((0, 24, W, 24), fill=(120, 200, 255))


def _symbian_panel(d, x0, y0, x1, y1, r, color, outline, width):
    """Panneau S60 : bleu arrondi, plus clair en haut, liseré bleu clair et reflet."""
    if x1 - x0 < 4 or y1 - y0 < 4:
        d.rounded_rectangle((x0, y0, x1, y1), r, fill=color)
        return
    top = R.mix(color, (255, 255, 255), 0.12)
    bottom = R.mix(color, (0, 0, 0), 0.25)
    w, h = x1 - x0 + 1, y1 - y0 + 1

    def make():                       # dégradé vertical clair → couleur → sombre
        col = Image.new("RGB", (1, h))
        for k in range(h):
            f = k / max(1, h - 1)
            col.putpixel((0, k), R.mix(top, color, f * 2) if f < 0.5
                         else R.mix(color, bottom, (f - 0.5) * 2))
        return col.resize((w, h))
    grad = _cached(("sym_grad", w, h, color), make)
    d._image.paste(grad, (x0, y0), _mask(w, h, r))   # pile dans l'arrondi, coins compris
    d.rounded_rectangle((x0, y0, x1, y1), r, outline=outline or R.mix(color, (150, 210, 255), 0.45),
                        width=width)
    d.line((x0 + r, y0 + 1, x1 - r, y0 + 1), fill=R.mix(top, (255, 255, 255), 0.35))


def _symbian_bar(d, x, y, w, h, fw, color):
    """Barre de progression S60 : piste sombre arrondie, remplissage vif et brillant."""
    r = max(1, h // 2)
    d.rounded_rectangle((x, y, x + w, y + h), r, fill=(6, 24, 58),
                        outline=R.mix((6, 24, 58), (120, 180, 240), 0.35))
    if fw < 2:
        return
    d.rounded_rectangle((x, y, x + fw, y + h), r, fill=color)
    if h >= 4:
        d.line((x + r, y + 1, x + fw - r, y + 1), fill=R.mix(color, (255, 255, 255), 0.55))


# --- dernière passe ------------------------------------------------------------------------------

PIXEL_PALETTE = [(12, 12, 28), (36, 36, 76), (76, 76, 124), (188, 188, 204), (252, 252, 252),
                 (60, 188, 252), (0, 112, 236), (248, 120, 88), (184, 120, 248), (88, 216, 84),
                 (0, 168, 0), (248, 184, 0), (240, 40, 88), (252, 160, 68), (104, 136, 252),
                 (184, 248, 24), (124, 64, 0), (0, 0, 0)]


def postprocess(img, name):
    if name in ("tron", "hud"):
        bright = img.point(lambda v: max(0, v - (110 if name == "tron" else 140)) * 2)
        glow = bright.filter(ImageFilter.GaussianBlur(3 if name == "tron" else 2))
        return ImageChops.add(img, glow, scale=1.5 if name == "tron" else 2.2)
    if name == "pixel":
        pal = _cached("pixel_pal", lambda: _palette_image(PIXEL_PALETTE))
        return img.quantize(palette=pal, dither=Image.Dither.NONE).convert("RGB")
    return None


def _palette_image(colors):
    p = Image.new("P", (1, 1))
    flat = [v for c in colors for v in c]
    p.putpalette(flat + flat[-3:] * (256 - len(colors)))
    return p
