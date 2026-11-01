"""Pages de l'écran monochrome 160×43 des G15 / G510 / G13 (version « G15 Monitor »).

Image en mode "1" : 1 = pixel allumé (sombre sur l'écran rétroéclairé du clavier). Chaque
page a un bandeau de titre inversé (nom de la page, position, heure) puis 3 lignes en Tahoma
10 px, rendue par Windows sans lissage (nette, contrairement à FreeType) ; les chiffres
principaux sont plus grands, en Tahoma gras. Pas de couleur, de dégradé ni de pochette.

Les 4 touches sous l'écran : ◄ et ► changent de page, les deux autres dépendent de la page
(lecture / suivant sur Média, volume sur Audio) ; leurs rôles s'affichent un instant en bas
dès qu'on en presse une."""
import time

from PIL import Image, ImageDraw

from .gdifont import GdiFont

W, H = 160, 43
HEAD = 11                 # bandeau de titre (y 0 à 10)
TOP = 12                  # haut du contenu : 3 lignes de 10 px (12, 22, 32)
LINE = 10

PAGES = {"clock": "Horloge", "system": "Système", "gpu": "GPU", "media": "Média",
         "audio": "Audio", "claude": "Claude", "weather": "Météo", "network": "Réseau"}
DEFAULT_PAGES = ["clock", "system", "gpu", "media", "audio", "claude", "weather", "network"]

JOURS = ("lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche")
JOURS_COURTS = ("lun.", "mar.", "mer.", "jeu.", "ven.", "sam.", "dim.")
MOIS = ("janv.", "févr.", "mars", "avr.", "mai", "juin", "juil.", "août", "sept.", "oct.",
        "nov.", "déc.")

_fonts = {}


def _gdi(face, size, bold=False):
    key = (face, size, bold)
    if key not in _fonts:
        _fonts[key] = GdiFont(face, size, bold)
    return _fonts[key]


def small(bold=False):
    """Texte courant : Tahoma 10 px rendue par Windows (la plus lisible à cette taille)."""
    return _gdi("Tahoma", 10, bold)


def big(size):
    """Grands chiffres : Tahoma gras (vraiment grasse à partir de 17 px)."""
    return _gdi("Tahoma", size, True)


def font(size=0, bold=False):
    return small(bold) if size < 12 else big(size)


# signes courants qui s'affichent mal → équivalents
_TRANS = str.maketrans({"…": "...", "—": "-", "–": "-", "−": "-", "’": "'", "‘": "'",
                        "“": '"', "”": '"', " ": " ", " ": " "})


def clean(s):
    return (s or "").translate(_TRANS)


def canvas():
    img = Image.new("1", (W, H), 0)
    return img, ImageDraw.Draw(img)


def text(d, xy, s, anchor="la", f=None, fill=1):
    """Texte rendu par Windows, placé selon `anchor` (comme PIL : l/m/r puis a/m/s/b)."""
    s = clean(s)
    f = f or small()
    x, y = xy
    w = f.textlength(s)
    x -= {"l": 0, "m": w / 2, "r": w}.get(anchor[0], 0)
    y -= {"a": 0, "t": 0, "m": f.cell / 2, "s": f.ascent, "b": f.cell,
          "d": f.cell}.get(anchor[1], 0)
    f.draw(d._image, round(x), round(y), s, fill)


def line(d, k, s, anchor="la", x=None, f=None, fill=1):
    """Texte sur la ligne de contenu k (0 à 2), centré verticalement dans ses 10 px."""
    f = f or small()
    y = TOP + k * LINE + LINE // 2
    text(d, (x if x is not None else (W if anchor[0] == "r" else 0), y), s, anchor[0] + "m",
         f, fill)


def fit(d, s, f, width):
    s = clean(s)
    f = f or small()
    if f.textlength(s) <= width:
        return s
    while s and f.textlength(s + "...") > width:
        s = s[:-1]
    return s.rstrip() + "..."


def marquee(img, s, x, y, width, t, f=None):
    """Texte qui défile s'il est trop long (pause au début), coupé net à `width`."""
    s = clean(s)
    f = f or small()
    tw = f.textlength(s)
    if tw <= width:
        f.draw(img, x, y, s)
        return
    gap = 24
    period = (tw + gap) / 18 + 2           # 18 px/s, 2 s d'arrêt au début
    off = int(max(0.0, (t % period) - 2) * 18)
    strip = Image.new("1", (width, f.cell), 0)
    f.draw(strip, -off, 0, s)
    f.draw(strip, -off + tw + gap, 0, s)
    img.paste(strip, (x, y))


def bar(d, x, y, w, h, frac):
    frac = max(0.0, min(1.0, frac or 0.0))
    d.rectangle((x, y, x + w - 1, y + h - 1), outline=1)
    fw = int((w - 4) * frac)
    if fw > 0:
        d.rectangle((x + 2, y + 2, x + 1 + fw, y + h - 3), fill=1)


def line_bar(d, k, x, w, frac):
    """Barre de 7 px de haut sur la ligne de contenu k."""
    bar(d, x, TOP + k * LINE + 1, w, 8, frac)


def num(v, fmt="{:.0f}", suffix=""):
    return "—" if v is None else fmt.format(v) + suffix


def rate(bps):
    """Débit en octets/s → texte court."""
    if bps >= 1e6:
        return f"{bps / 1e6:.1f} Mo/s".replace(".", ",")
    return f"{bps / 1e3:.0f} Ko/s"


def fmt_time(sec):
    sec = int(max(0, sec))
    return f"{sec // 60}:{sec % 60:02d}"


def header(img, d, title, t, index=None, count=None, right=None):
    """Bandeau inversé : titre de la page à gauche, position « 3/8 » et heure à droite."""
    d.rectangle((0, 0, W - 1, HEAD - 1), fill=1)
    f, fb = small(), small(True)
    right = right if right is not None else time.strftime("%H:%M", time.localtime(t))
    rw = f.textlength(right)
    text(d, (W - 2, HEAD // 2), right, "rm", f, 0)
    pos = f"{index + 1}/{count}" if index is not None and count else ""
    pw = f.textlength(pos) if pos else 0
    if pos:
        text(d, (W - 2 - rw - 8, HEAD // 2), pos, "rm", f, 0)
    room = W - 4 - rw - (pw + 12 if pos else 6)
    text(d, (2, HEAD // 2), fit(d, title, fb, room), "lm", fb, 0)


# --- pages ------------------------------------------------------------------------------------

def page_clock(img, d, c, t):
    lt = time.localtime(t)
    hm, f = time.strftime("%H:%M", lt), big(20)
    text(d, (2, TOP + 15), hm, "lm", f)
    # les secondes juste après, plus petites, calées sur le bas des chiffres
    sx = 2 + f.textlength(hm) + 1
    text(d, (sx, TOP + 15 - f.cell / 2 + f.ascent), f":{lt.tm_sec:02d}", "ls", small(True))
    x = 98
    line(d, 0, f"{lt.tm_mday} {MOIS[lt.tm_mon - 1]}", x=x)
    line(d, 1, str(lt.tm_year), x=x)
    w = c.weather
    cur = w.current() if w and getattr(w, "data", None) else None
    if cur:
        place = ((w.place or {}).get("name") or "").split(",")[0]
        line(d, 2, fit(d, f"{place} {cur['temperature_2m']:.0f}°".strip(), small(), W - x), x=x)


def title_clock(c, t):
    lt = time.localtime(t)
    return JOURS[lt.tm_wday].capitalize(), ""


def page_system(img, d, c, t):
    st, s = c.stats, (c.gpu.s if c.gpu else {})
    ram = st.ram
    rows = (("CPU", st.cpu, num(s.get("cpu_temp"), suffix="°")),
            ("GPU", s.get("load", st.gpu), num(s.get("temp"), suffix="°")),
            ("RAM", ram.percent, f"{ram.used / 2**30:.0f}/{ram.total / 2**30:.0f} Go"))
    for k, (label, pct, extra) in enumerate(rows):
        line(d, k, label, f=small(True))
        line_bar(d, k, 27, 58, (pct or 0) / 100)
        line(d, k, f"{pct or 0:.0f} %", x=90)
        line(d, k, extra, "rm")


def page_gpu(img, d, c, t):
    g = c.gpu
    s = g.s if g else {}
    game = g.game if g else None
    if game and game.get("fps"):
        text(d, (0, TOP + 9), f"{game['fps']:.0f}", "lm", big(17))
        line(d, 2, "FPS", f=small(True))
    else:
        text(d, (0, TOP + 9), f"{s.get('load', 0):.0f}%", "lm", big(17))
        line(d, 2, "charge", f=small(True))
    x = 70
    temp = num(s.get("temp"), suffix="°")
    if s.get("hotspot"):
        temp += f" / {s['hotspot']:.0f}°"
    for k, (label, value) in enumerate((("Temp.", temp),
                                        ("Charge", num(s.get("load"), suffix=" %")),
                                        ("Conso.", num(s.get("power"), suffix=" W")))):
        line(d, k, label, x=x)
        line(d, k, value, "rm", f=small(True))


def title_gpu(c, t):
    game = c.gpu.game if c.gpu else None
    if game:
        return game["name"].rsplit(".", 1)[0], None
    return "GPU", None


def page_media(img, d, c, t):
    m = c.media
    if not m or not (m.title or m.artist):
        text(d, (W // 2, TOP + 9), "rien ne joue en ce moment", "mm")
        return
    y0 = TOP + (LINE - small(True).cell) // 2
    if m.playing:                          # ▶ ou ❚❚
        d.polygon([(0, TOP + 1), (0, TOP + 8), (4, TOP + 4)], fill=1)
    else:
        d.rectangle((0, TOP + 1, 1, TOP + 8), fill=1)
        d.rectangle((3, TOP + 1, 4, TOP + 8), fill=1)
    marquee(img, m.title or "", 8, y0, W - 8, t, small(True))
    line(d, 1, fit(d, m.artist or "", small(), W - 8), x=8)
    pos, dur = m.position_at(t), m.duration
    if dur:
        a, b = fmt_time(pos), "-" + fmt_time(dur - pos)
        f = small()
        aw, bw = f.textlength(a), f.textlength(b)
        line(d, 2, a)
        line(d, 2, b, "rm")
        line_bar(d, 2, aw + 4, W - aw - bw - 8, pos / dur)


def title_media(c, t):
    m = c.media
    return ((m.app if m and m.app else "Média"), None)


def page_audio(img, d, c, t):
    v = c.volume
    if not v or v.level is None:
        text(d, (W // 2, TOP + 15), "audio indisponible", "mm")
        return
    speaker(d, 0, TOP + 5, v.muted)
    line(d, 0, "muet" if v.muted else f"{v.level * 100:.0f} %", x=16, f=small(True))
    line_bar(d, 0, 52, W - 52, 0 if v.muted else v.level)
    line(d, 1, fit(d, v.device or "Sortie", small(), W))
    if v.mic_level is not None:
        line(d, 2, "micro coupé" if v.mic_muted else f"micro {v.mic_level * 100:.0f} %",
             f=small(v.mic_muted))


def speaker(d, x, cy, muted):
    d.rectangle((x, cy - 2, x + 2, cy + 2), fill=1)
    d.polygon([(x + 2, cy - 2), (x + 6, cy - 5), (x + 6, cy + 5), (x + 2, cy + 2)], fill=1)
    if muted:
        d.line((x + 8, cy - 3, x + 12, cy + 3), fill=1)
        d.line((x + 8, cy + 3, x + 12, cy - 3), fill=1)
    else:
        d.arc((x + 4, cy - 5, x + 11, cy + 5), 300, 60, fill=1)


STATES = {"working": "travaille", "waiting": "attend", "idle": "fini", "stale": "silencieux"}


def page_claude(img, d, c, t):
    sessions = c.sessions or []
    if not sessions:
        text(d, (W // 2, TOP + 15), "aucune session Claude Code", "mm")
        return
    for k, s in enumerate(sessions[:3]):
        y = TOP + k * LINE
        state = s.state or "idle"
        if state == "working":            # point qui clignote
            if int(t * 2) % 2 == 0:
                d.ellipse((0, y + 2, 5, y + 7), fill=1)
            else:
                d.ellipse((0, y + 2, 5, y + 7), outline=1)
        elif state == "waiting":
            d.rectangle((0, y + 1, 5, y + 8), fill=1)
            d.point((2, y + 7), fill=0)
            d.line((2, y + 2, 2, y + 5), fill=0)
        else:
            d.ellipse((0, y + 2, 5, y + 7), outline=1)
        line(d, k, fit(d, s.name or "?", small(True), 70), x=9, f=small(True))
        detail = s.message if state == "waiting" and s.message else \
            (s.tool if state == "working" and s.tool else STATES.get(state, state))
        line(d, k, fit(d, detail or "", small(), 76), "rm")


def title_claude(c, t):
    n = len([s for s in c.sessions or [] if s.state in ("working", "waiting")])
    return ("Claude" + (f" · {n} actif{'s' if n > 1 else ''}" if n else "")), None


def page_weather(img, d, c, t):
    w = c.weather
    cur = w.current() if w and getattr(w, "data", None) else None
    if not cur:
        text(d, (W // 2, TOP + 15), "chargement de la météo…", "mm")
        return
    from .weather import describe
    text(d, (0, TOP + 9), f"{cur['temperature_2m']:.0f}°", "lm", big(17))
    x = 46
    line(d, 0, fit(d, describe(cur["weather_code"])[0], small(True), W - x), x=x,
         f=small(True))
    line(d, 1, f"ressenti {cur.get('apparent_temperature', cur['temperature_2m']):.0f}°",
         x=x)
    days = w.days(2)
    parts = []
    for k, (day, _code, hi, lo, *_rest) in enumerate(days):
        lt = time.localtime(day) if isinstance(day, (int, float)) else None
        name = "auj." if k == 0 else (JOURS_COURTS[lt.tm_wday] if lt else str(day)[5:])
        parts.append(f"{name} {hi:.0f}/{lo:.0f}°")
    line(d, 2, "   ".join(parts))


def title_weather(c, t):
    w = c.weather
    return ((w.place or {}).get("name") or "Météo") if w else "Météo", None


def page_network(img, d, c, t):
    st = c.stats
    arrow(d, 2, TOP + 5, False)
    line(d, 0, "Réception", x=9)
    line(d, 0, rate(st.net_down), "rm", f=small(True))
    arrow(d, 2, TOP + LINE + 5, True)
    line(d, 1, "Envoi", x=9)
    line(d, 1, rate(st.net_up), "rm", f=small(True))
    line(d, 2, "Disque", x=9)
    line(d, 2, rate(st.disk_read + st.disk_write), "rm", f=small(True))


def title_network(c, t):
    up = int(t - c.stats.boot)
    since = f"{up // 86400} j {up % 86400 // 3600} h" if up >= 86400 else \
        f"{up // 3600} h {up % 3600 // 60:02d}"
    return f"Réseau · allumé {since}", None


def arrow(d, cx, cy, up):
    """Petite flèche ↑ / ↓ dessinée."""
    if up:
        d.polygon([(cx - 2, cy - 1), (cx + 2, cy - 1), (cx, cy - 4)], fill=1)
        d.line((cx, cy - 1, cx, cy + 3), fill=1)
    else:
        d.polygon([(cx - 2, cy + 1), (cx + 2, cy + 1), (cx, cy + 4)], fill=1)
        d.line((cx, cy - 3, cx, cy + 1), fill=1)


PAGE_FUNCS = {"clock": page_clock, "system": page_system, "gpu": page_gpu, "media": page_media,
              "audio": page_audio, "claude": page_claude, "weather": page_weather,
              "network": page_network}
# titre du bandeau selon la page : (titre, texte de droite ou None pour l'heure)
TITLES = {"clock": title_clock, "gpu": title_gpu, "media": title_media, "claude": title_claude,
          "weather": title_weather, "network": title_network}

# rôles des deux touches de droite, selon la page (les deux de gauche changent de page) ;
# "playpause" et "next" sont dessinés
ACTIONS = {"media": ("playpause", "next"), "audio": ("vol -", "vol +")}


# --- par-dessus les pages -----------------------------------------------------------------------

def overlay_box(img, d, x0, y0, x1, y1):
    """Encadré inversé (fond allumé) avec une marge éteinte autour, lisible sur toute page."""
    d.rectangle((x0 - 1, y0 - 1, x1 + 1, y1 + 1), fill=0)
    d.rectangle((x0, y0, x1, y1), fill=1)


def draw_banner(img, d, title, body):
    """Bandeau de notification : tout le contenu, inversé, sous le titre de la page."""
    overlay_box(img, d, 0, TOP, W - 1, H - 1)
    text(d, (3, TOP + 8), fit(d, title, small(True), W - 6), "lm", small(True), 0)
    text(d, (3, TOP + 22), fit(d, body, small(), W - 6), "lm", small(), 0)


def draw_volume(img, d, level, muted, label="Volume"):
    overlay_box(img, d, 16, TOP + 2, W - 17, H - 3)
    text(d, (21, TOP + 8), label, "lm", small(True), 0)
    text(d, (W - 21, TOP + 8), "muet" if muted else f"{level * 100:.0f} %", "rm", small(True),
         0)
    d.rectangle((21, TOP + 16, W - 22, TOP + 23), outline=0)
    fw = int((W - 47) * (0 if muted else level))
    if fw > 0:
        d.rectangle((23, TOP + 18, 23 + fw, TOP + 21), fill=0)


def draw_keys(img, d, page):
    """Rôles des 4 touches, en bas de l'écran."""
    labels = ("prev_page", "next_page") + ACTIONS.get(page, ("", ""))
    overlay_box(img, d, 0, H - 10, W - 1, H - 1)
    cw = W // 4
    cy = H - 5
    for k, lab in enumerate(labels):
        cx = k * cw + cw // 2
        if k:
            d.line((k * cw, H - 9, k * cw, H - 2), fill=0)
        if lab == "prev_page":
            d.polygon([(cx + 2, cy - 3), (cx + 2, cy + 3), (cx - 2, cy)], fill=0)
        elif lab == "next_page":
            d.polygon([(cx - 2, cy - 3), (cx - 2, cy + 3), (cx + 2, cy)], fill=0)
        elif lab == "playpause":
            d.polygon([(cx - 6, cy - 3), (cx - 6, cy + 3), (cx - 2, cy)], fill=0)
            d.rectangle((cx + 1, cy - 3, cx + 2, cy + 3), fill=0)
            d.rectangle((cx + 4, cy - 3, cx + 5, cy + 3), fill=0)
        elif lab == "next":
            d.polygon([(cx - 4, cy - 3), (cx - 4, cy + 3), (cx, cy)], fill=0)
            d.polygon([(cx, cy - 3), (cx, cy + 3), (cx + 4, cy)], fill=0)
            d.rectangle((cx + 4, cy - 3, cx + 5, cy + 3), fill=0)
        elif lab:
            text(d, (cx, cy), lab, "mm", small(), 0)


def draw_page_dots(d, index, count):
    """Ancien repère de page : la position est maintenant dans le bandeau de titre."""


def render(page, c, t=None, index=None, count=None):
    t = t or time.time()
    img, d = canvas()
    PAGE_FUNCS.get(page, page_clock)(img, d, c, t)
    title, right = (TITLES[page](c, t) if page in TITLES else (PAGES.get(page, page), None))
    header(img, d, title, t, index, count, right)
    return img


def lcd_style(img, scale=3, lit=(30, 34, 28), back=(158, 190, 90)):
    """Aperçu façon écran du clavier (pixels sombres sur fond rétroéclairé), agrandi."""
    rgb = Image.new("RGB", img.size, back)
    rgb.paste(Image.new("RGB", img.size, lit), (0, 0), img.convert("L"))
    return rgb.resize((img.width * scale, img.height * scale), Image.NEAREST)
