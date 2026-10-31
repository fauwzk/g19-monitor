"""Liste des écrans (touche Menu), au choix (réglage screen_list_style) :
  coverflow : miniatures en perspective avec leur reflet ;
  flat      : cartes à plat qui défilent ;
  grid      : mosaïque de miniatures, ▲ ▼ changent de ligne ;
  list      : noms à gauche, aperçu de l'écran choisi à droite.
◄ ► (et ▲ ▼) choisissent, OK ouvre l'écran (ou les paramètres), Menu / Annuler ferment. La
carte choisie est rendue en direct, les autres sont rafraîchies à tour de rôle."""
import math

from PIL import Image, ImageDraw

from . import render as R
from .settings import PAGE_TITLES

CARD_W, CARD_H = 184, 138
STYLES = {"coverflow": "coverflow", "flat": "cartes à plat", "grid": "grille",
          "list": "liste et aperçu"}
GRID_COLS, GRID_W, GRID_H, GRID_ROW = 3, 96, 72, 92
LIST_ROWS, LIST_ROW = 8, 24
CENTER_Y = 104
SETTINGS = "__settings__"


def _solve(a, b):
    """Résout a·x = b (8×8) par élimination de Gauss."""
    n = len(b)
    m = [row[:] + [b[i]] for i, row in enumerate(a)]
    for col in range(n):
        piv = max(range(col, n), key=lambda r: abs(m[r][col]))
        m[col], m[piv] = m[piv], m[col]
        for r in range(n):
            if r != col and m[col][col]:
                f = m[r][col] / m[col][col]
                for k in range(col, n + 1):
                    m[r][k] -= f * m[col][k]
    return [m[i][n] / m[i][i] for i in range(n)]


def _coeffs(dst, src):
    """Coefficients PERSPECTIVE de Pillow : point de sortie (dst) → point source (src)."""
    a, b = [], []
    for (x, y), (u, v) in zip(dst, src):
        a.append([x, y, 1, 0, 0, 0, -u * x, -u * y])
        b.append(u)
        a.append([0, 0, 0, x, y, 1, -v * x, -v * y])
        b.append(v)
    return _solve(a, b)


class Coverflow:
    def __init__(self):
        self.open = False
        self.cards = []          # pages, puis SETTINGS
        self.index = 0
        self.pos = 0.0           # position affichée (glisse vers index)
        self.thumbs = {}
        self.style = "coverflow"
        self._small = {}         # (carte, taille) → (miniature source, réduction)
        self._turn = 0
        self._mask = Image.new("L", (CARD_W, CARD_H), 255)
        self._fade = Image.linear_gradient("L").resize((CARD_W, CARD_H // 3)) \
            .point(lambda v: max(0, 80 - v * 80 // 255)).transpose(Image.FLIP_TOP_BOTTOM)

    def show(self, pages, current, style="coverflow"):
        self.style = style if style in STYLES else "coverflow"
        self.cards = list(pages) + [SETTINGS]
        self.index = self.cards.index(current) if current in self.cards else 0
        self.pos = float(self.index)
        self.thumbs = {}
        self.open = True

    def handle(self, button):
        """("page", nom) ou ("settings",) quand une carte est ouverte, sinon None."""
        if button in ("menu", "cancel"):
            self.open = False
        elif button in ("up", "down") and self.style == "grid":
            step = GRID_COLS if button == "down" else -GRID_COLS
            self.index = max(0, min(len(self.cards) - 1, self.index + step))
        elif button in ("left", "up"):
            self.index = (self.index - 1) % len(self.cards)
        elif button in ("right", "down"):
            self.index = (self.index + 1) % len(self.cards)
        elif button == "ok":
            self.open = False
            card = self.cards[self.index]
            return ("settings",) if card == SETTINGS else ("page", card)
        return None

    # --- rendu ---

    def _thumb(self, card, c, t, menu_preview):
        if card == SETTINGS:
            img = menu_preview()
        else:
            img = R.render(card, c, t, post=False)
        return img.resize((CARD_W, CARD_H), Image.LANCZOS)

    def _refresh(self, c, t, menu_preview):
        center = self.cards[self.index]
        if not self.thumbs:              # première ouverture : toutes les miniatures
            for card in self.cards:
                self.thumbs[card] = self._thumb(card, c, t, menu_preview)
            return
        self.thumbs[center] = self._thumb(center, c, t, menu_preview)
        # une miniature voisine rafraîchie par image, à tour de rôle
        self._turn = (self._turn + 1) % len(self.cards)
        other = self.cards[self._turn]
        if other != center:
            self.thumbs[other] = self._thumb(other, c, t, menu_preview)

    def _small_thumb(self, card, w, h):
        """Miniature réduite (mise en cache tant que la grande ne change pas)."""
        big = self.thumbs.get(card)
        if big is None:
            return None
        hit = self._small.get((card, w, h))
        if hit and hit[0] is big:
            return hit[1]
        small = big.resize((w, h), Image.BILINEAR)
        self._small[(card, w, h)] = (big, small)
        return small

    def _title(self, card):
        return "Paramètres" if card == SETTINGS else PAGE_TITLES.get(card, card)

    def _frame(self, d, hint):
        R.title_bar(d)
        d.text((8, 12), "Écrans", font=R.font(14, True), fill=R.TEXT, anchor="lm")
        d.text((R.W - 8, 12), hint, font=R.font(9), fill=R.MUTED, anchor="rm")

    def render(self, c, t, menu_preview):
        R.apply_theme(c)
        self._refresh(c, t, menu_preview)
        if self.style == "grid":
            return self._render_grid(t)
        if self.style == "list":
            return self._render_list(t)
        if self.style == "flat":
            return self._render_flat(t)
        return self._render_coverflow()

    def _render_grid(self, t):
        img = R.canvas()
        d = ImageDraw.Draw(img)
        self._frame(d, "◄ ► ▲ ▼ choisir · OK ouvrir · Menu fermer")
        n = len(self.cards)
        rows = (n + GRID_COLS - 1) // GRID_COLS
        row = self.index // GRID_COLS
        top = R.glide("cf_grid_top", max(0, min(row - 1, rows - 2)) * GRID_ROW, t, 0.09)
        x0 = (R.W - GRID_COLS * (GRID_W + 8) + 8) // 2
        sel_x = x0 + (self.index % GRID_COLS) * (GRID_W + 8)
        sel_y = 32 + row * GRID_ROW - top
        gx = R.glide("cf_grid_x", sel_x, t)
        gy = R.glide("cf_grid_y", sel_y, t)
        R.panel(d, (gx - 4, gy - 4, gx + GRID_W + 4, gy + GRID_H + 16), 6,
                color=R.dim(R.ACCENT, 0.35))
        for i, card in enumerate(self.cards):
            x = x0 + (i % GRID_COLS) * (GRID_W + 8)
            y = 32 + (i // GRID_COLS) * GRID_ROW - top
            if y < 20 or y > 224:
                continue
            th = self._small_thumb(card, GRID_W, GRID_H)
            if th is not None:
                if i != self.index:
                    th = Image.eval(th, lambda v: int(v * 0.7))
                img.paste(th, (int(x), int(y)))
            d.text((x + GRID_W // 2, y + GRID_H + 7), self._title(card),
                   font=R.font(10, i == self.index),
                   fill=R.TEXT if i == self.index else R.MUTED, anchor="mm")
        return R.postprocess(img)

    def _render_list(self, t):
        img = R.canvas()
        d = ImageDraw.Draw(img)
        self._frame(d, "▲ ▼ choisir · OK ouvrir · Menu fermer")
        n = len(self.cards)
        top = R.glide("cf_list_top", max(0, min(self.index - LIST_ROWS // 2, n - LIST_ROWS))
                      * LIST_ROW, t, 0.09)
        gy = R.glide("cf_list_y", 32 + self.index * LIST_ROW - top, t)
        R.panel(d, (4, gy, 140, gy + LIST_ROW - 2), 6, color=R.dim(R.ACCENT, 0.35))
        for i, card in enumerate(self.cards):
            y = 32 + i * LIST_ROW - top
            if y < 26 or y > 222:
                continue
            sel = i == self.index
            d.text((14, y + LIST_ROW // 2 - 1), R.fit(d, self._title(card), R.font(12, sel), 120),
                   font=R.font(12, sel), fill=R.TEXT if sel else R.MUTED, anchor="lm")
        # aperçu de l'écran choisi, en direct
        card = self.cards[self.index]
        th = self._small_thumb(card, 168, 126)
        R.panel(d, (146, 38, 316, 166), 6)
        if th is not None:
            img.paste(th, (147, 39))
        d.rectangle((146, 38, 315, 165), outline=R.ACCENT)
        d.text((231, 182), self._title(card), font=R.font(14, True), fill=R.TEXT, anchor="mm")
        d.text((231, 200), f"{self.index + 1} / {n}", font=R.font(9), fill=R.MUTED, anchor="mm")
        return R.postprocess(img)

    def _render_flat(self, t):
        n = len(self.cards)
        diff = (self.index - self.pos + n / 2) % n - n / 2
        self.pos = (self.pos + diff * 0.35) % n if abs(diff) > 0.01 else float(self.index)
        img = R.canvas()
        d = ImageDraw.Draw(img)
        self._frame(d, "◄ ► choisir · OK ouvrir · Menu fermer")
        items = []
        for i, card in enumerate(self.cards):
            k = (i - self.pos + n / 2) % n - n / 2
            if abs(k) <= 2.2:
                items.append((abs(k), k, card))
        for _, k, card in sorted(items, reverse=True):
            a = min(abs(k), 1.0)
            s = 1 - 0.28 * a
            w, h = int(CARD_W * s), int(CARD_H * s)
            th = self._small_thumb(card, w, h)
            if th is None:
                continue
            if abs(k) > 0.05:
                th = Image.eval(th, lambda v, f=1 - 0.45 * a: int(v * f))
            cx = R.W / 2 + k * 150
            y = 110 - h // 2
            img.paste(th, (int(cx - w / 2), y))
            if abs(k) < 0.3:
                d.rectangle((int(cx - w / 2), y, int(cx + w / 2) - 1, y + h - 1),
                            outline=R.ACCENT)
        card = self.cards[self.index]
        d.text((R.W // 2, 200), self._title(card), font=R.font(15, True), fill=R.TEXT,
               anchor="mm")
        x0 = R.W // 2 - (n - 1) * 4
        for i in range(n):
            d.ellipse((x0 + i * 8 - 1.5, 222, x0 + i * 8 + 1.5, 225),
                      fill=R.ACCENT if i == self.index else R.TRACK)
        return R.postprocess(img)

    def _render_coverflow(self):
        # glissement : la position rattrape l'index (au plus court, la liste boucle)
        n = len(self.cards)
        diff = (self.index - self.pos + n / 2) % n - n / 2
        self.pos = (self.pos + diff * 0.35) % n if abs(diff) > 0.01 else float(self.index)

        img = R.canvas()
        d = ImageDraw.Draw(img)
        # sol : léger dégradé sous les cartes
        floor_y = CENTER_Y + CARD_H // 2 + 2
        img.paste(R._vgrad(R.W, R.H - floor_y, R.mix(R.BG, R.ACCENT, 0.06), R.BG), (0, floor_y))
        R.title_bar(d)
        d.text((8, 12), "Écrans", font=R.font(14, True), fill=R.TEXT, anchor="lm")
        d.text((R.W - 8, 12), "◄ ► choisir · OK ouvrir · Menu fermer", font=R.font(9),
               fill=R.MUTED, anchor="rm")

        items = []
        for i, card in enumerate(self.cards):
            k = (i - self.pos + n / 2) % n - n / 2
            if abs(k) <= 2.6:
                items.append((abs(k), k, card))
        for _, k, card in sorted(items, reverse=True):     # du plus loin au plus proche
            self._draw_card(img, self.thumbs.get(card), k, floor_y)

        card = self.cards[self.index]
        title = "Paramètres" if card == SETTINGS else PAGE_TITLES.get(card, card)
        d.text((R.W // 2, 206), title, font=R.font(15, True), fill=R.TEXT, anchor="mm")
        d.text((R.W // 2, 224), f"{self.index + 1} / {n}", font=R.font(9), fill=R.MUTED,
               anchor="mm")
        # petits points de position
        x0 = R.W // 2 - (n - 1) * 4
        for i in range(n):
            d.ellipse((x0 + i * 8 - 1.5, 233, x0 + i * 8 + 1.5, 236),
                      fill=R.ACCENT if i == self.index else R.TRACK)
        return R.postprocess(img)

    def _draw_card(self, img, thumb, k, floor_y):
        if thumb is None:
            return
        a = min(abs(k), 1.0)
        far = max(0.0, abs(k) - 1.0)
        scale = 1 - 0.3 * a - 0.12 * far
        h = CARD_H * scale
        w = CARD_W * scale * (1 - 0.32 * a)          # raccourci de perspective
        skew = 0.18 * a                              # bord extérieur plus court
        cx = R.W / 2 + math.copysign(128 * a + 50 * far, k)
        bottom = floor_y
        top = bottom - h
        x0, x1 = cx - w / 2, cx + w / 2
        inner, outer = (h, h * (1 - skew))
        if k >= 0:   # carte à droite : bord gauche (intérieur) plein, bord droit raccourci
            lh, rh = inner, outer
        else:
            lh, rh = outer, inner
        mid = top + h / 2
        quad = [(x0, mid - lh / 2), (x0, mid + lh / 2), (x1, mid + rh / 2), (x1, mid - rh / 2)]
        bx0, by0 = int(math.floor(min(p[0] for p in quad))), int(math.floor(top))
        bw, bh = int(math.ceil(w)) + 2, int(math.ceil(h)) + 2
        local = [(px - bx0, py - by0) for px, py in quad]
        src = [(0, 0), (0, CARD_H), (CARD_W, CARD_H), (CARD_W, 0)]
        coeffs = _coeffs(local, src)
        card = thumb.transform((bw, bh), Image.PERSPECTIVE, coeffs, Image.BILINEAR)
        mask = self._mask.transform((bw, bh), Image.PERSPECTIVE, coeffs, Image.BILINEAR,
                                    fillcolor=0)
        shade = 1 - 0.5 * min(abs(k), 1.6) / 1.6
        if shade < 0.99:
            card = Image.eval(card, lambda v, s=shade: int(v * s))
        img.paste(card, (bx0, by0), mask)
        # reflet : la carte retournée, estompée, sous le sol
        refl_src = thumb.transpose(Image.FLIP_TOP_BOTTOM)
        rh_px = int(bh * 0.33)
        if rh_px > 2:
            rcard = refl_src.transform((bw, bh), Image.PERSPECTIVE, coeffs, Image.BILINEAR) \
                .crop((0, 0, bw, rh_px))
            rmask = mask.crop((0, 0, bw, rh_px))
            fade = Image.linear_gradient("L").resize((bw, rh_px)) \
                .point(lambda v, s=shade: int(max(0, 70 - v * 70 // 255) * s))
            from PIL import ImageChops
            img.paste(rcard, (bx0, int(by0 + bh)), ImageChops.multiply(rmask, fade))
        # liseré : la carte du centre est encadrée de l'accent
        if abs(k) < 0.3:
            ImageDraw.Draw(img).rectangle((bx0, by0, bx0 + bw - 2, by0 + bh - 2),
                                          outline=R.ACCENT)
