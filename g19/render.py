"""Rendu des pages 320x240 avec Pillow."""
import math
import re
import time

import psutil
from dataclasses import dataclass
from functools import lru_cache

from . import textfx

from PIL import Image, ImageChops, ImageDraw, ImageEnhance, ImageFilter, ImageFont, ImageStat

from .lcd import W, H
from .settings import PAGE_TITLES

# mode sombre à fort contraste : l'écran TFT du G19 écrase les tons proches
BG = (4, 6, 9)
PANEL = (24, 31, 40)
TRACK = (68, 80, 96)
TEXT = (250, 251, 253)
MUTED = (198, 206, 216)
ACCENT = (70, 220, 230)
GPU_C = (186, 140, 255)
RAM_C = (110, 185, 255)
OK = (80, 215, 105)
WARN = (245, 200, 75)
HOT = (255, 95, 85)
CLAUDE = (240, 135, 100)

STATE_COLOR = {"working": CLAUDE, "waiting": WARN, "idle": OK, "stale": MUTED}
STATE_LABEL = {"working": "travaille", "waiting": "attend ta réponse",
               "idle": "terminé", "stale": "inactif"}

JOURS = ["lun.", "mar.", "mer.", "jeu.", "ven.", "sam.", "dim."]
MOIS = ["janv.", "févr.", "mars", "avr.", "mai", "juin", "juil.", "août", "sept.", "oct.",
        "nov.", "déc."]

DISCORD = (88, 101, 242)
STEAM_BLUE = (102, 192, 244)
STEAM_GAME = (144, 186, 60)

# --- thèmes : les couleurs ci-dessus et celles de la météo sont remplacées à chaud ---
DARK = {"BG": BG, "PANEL": PANEL, "TRACK": TRACK, "TEXT": TEXT, "MUTED": MUTED,
        "ACCENT": ACCENT, "GPU_C": GPU_C, "RAM_C": RAM_C, "OK": OK, "WARN": WARN, "HOT": HOT,
        "CLAUDE": CLAUDE, "DISCORD": DISCORD, "STEAM_BLUE": STEAM_BLUE, "STEAM_GAME": STEAM_GAME,
        "SUN": (250, 196, 60), "MOON": (200, 210, 230), "CLOUD": (190, 200, 212),
        "CLOUD_DARK": (120, 130, 145), "RAIN": (88, 166, 255), "SNOW": (235, 240, 250)}
LIGHT = {"BG": (236, 239, 243), "PANEL": (255, 255, 255), "TRACK": (186, 195, 206),
         "TEXT": (16, 20, 26), "MUTED": (66, 74, 84), "ACCENT": (0, 104, 118),
         "GPU_C": (130, 80, 220), "RAM_C": (9, 105, 218), "OK": (26, 140, 60),
         "WARN": (190, 135, 0), "HOT": (210, 40, 50), "CLAUDE": (200, 95, 60),
         "DISCORD": (88, 101, 242), "STEAM_BLUE": (20, 110, 175), "STEAM_GAME": (70, 125, 15),
         "SUN": (235, 160, 0), "MOON": (110, 120, 150), "CLOUD": (150, 160, 175),
         "CLOUD_DARK": (100, 110, 125), "RAIN": (9, 105, 218), "SNOW": (150, 170, 200)}
# thème « G19 » : l'esprit de l'interface d'origine du clavier — noir profond, bandeau
# métal brossé, texte argent et bleu Logitech G
G19 = {**DARK, "BG": (0, 0, 0), "PANEL": (26, 30, 36), "TRACK": (68, 74, 84),
       "TEXT": (242, 245, 248), "MUTED": (182, 190, 200), "ACCENT": (20, 178, 245),
       "GPU_C": (90, 196, 255), "RAM_C": (176, 196, 216), "OK": (110, 214, 90),
       "WARN": (255, 186, 40), "HOT": (255, 72, 60)}
# Rétro G15 : dessiné en niveaux de gris (seule la luminosité compte), puis passé au filtre
# de l'écran monochrome ambre (voir postprocess)
G15 = {**DARK, "BG": (0, 0, 0), "PANEL": (34, 34, 34), "TRACK": (70, 70, 70),
       "TEXT": (255, 255, 255), "MUTED": (150, 150, 150), "ACCENT": (235, 235, 235),
       "GPU_C": (205, 205, 205), "RAM_C": (185, 185, 185), "OK": (215, 215, 215),
       "WARN": (240, 240, 240), "HOT": (255, 255, 255), "CLAUDE": (225, 225, 225),
       "DISCORD": (200, 200, 200), "STEAM_BLUE": (210, 210, 210), "STEAM_GAME": (230, 230, 230),
       "SUN": (255, 255, 255), "MOON": (200, 200, 200), "CLOUD": (170, 170, 170),
       "CLOUD_DARK": (110, 110, 110), "RAIN": (210, 210, 210), "SNOW": (240, 240, 240)}
# Néon : violet profond, cyan et magenta lumineux (avec une lueur, voir postprocess)
NEON = {**DARK, "BG": (9, 3, 20), "PANEL": (28, 12, 50), "TRACK": (82, 46, 120),
        "TEXT": (250, 244, 255), "MUTED": (206, 186, 234), "ACCENT": (0, 238, 255),
        "GPU_C": (255, 74, 206), "RAM_C": (172, 132, 255), "OK": (60, 255, 170),
        "WARN": (255, 222, 70), "HOT": (255, 60, 110), "CLAUDE": (255, 130, 90),
        "DISCORD": (130, 120, 255), "STEAM_BLUE": (90, 200, 255), "STEAM_GAME": (170, 255, 80)}
# Haut contraste : noir pur, blanc, jaune ; le plus lisible sur le LCD peu lumineux du G19
CONTRAST = {**DARK, "BG": (0, 0, 0), "PANEL": (22, 22, 22), "TRACK": (96, 96, 96),
            "TEXT": (255, 255, 255), "MUTED": (222, 222, 222), "ACCENT": (255, 222, 0),
            "GPU_C": (0, 214, 255), "RAM_C": (255, 140, 255), "OK": (0, 255, 110),
            "WARN": (255, 150, 0), "HOT": (255, 50, 50), "CLAUDE": (255, 150, 100),
            "DISCORD": (140, 150, 255), "STEAM_BLUE": (90, 210, 255),
            "STEAM_GAME": (170, 255, 60)}
# Glacier : bleu-gris froid et apaisé
GLACIER = {**DARK, "BG": (13, 19, 27), "PANEL": (29, 40, 53), "TRACK": (66, 84, 104),
           "TEXT": (238, 244, 250), "MUTED": (176, 194, 212), "ACCENT": (130, 210, 245),
           "GPU_C": (178, 160, 250), "RAM_C": (110, 176, 240), "OK": (130, 226, 170),
           "WARN": (246, 212, 110), "HOT": (250, 110, 124), "CLAUDE": (246, 164, 134),
           "DISCORD": (140, 152, 255), "STEAM_BLUE": (120, 200, 250),
           "STEAM_GAME": (170, 220, 110)}
# Braise : noir chaud et orange incandescent
BRAISE = {**DARK, "BG": (14, 7, 4), "PANEL": (40, 21, 13), "TRACK": (92, 52, 34),
          "TEXT": (255, 242, 230), "MUTED": (222, 188, 166), "ACCENT": (255, 146, 42),
          "GPU_C": (255, 96, 64), "RAM_C": (255, 204, 104), "OK": (178, 226, 92),
          "WARN": (255, 214, 64), "HOT": (255, 64, 52), "CLAUDE": (255, 170, 120),
          "DISCORD": (150, 150, 255), "STEAM_BLUE": (110, 196, 245),
          "STEAM_GAME": (190, 230, 90)}
# Terminal et Rouge nuit : dessinés en niveaux de gris comme le G15, puis teintés (phosphore
# vert à balayage, ou rouge qui n'éblouit pas la nuit) ; voir postprocess
TERMINAL = G15
NIGHT_RED = G15
# --- thèmes qui changent aussi la forme des éléments (voir looks.py) ---
AERO = {**DARK, "BG": (10, 24, 40), "PANEL": (30, 50, 72), "TRACK": (74, 100, 128),
        "TEXT": (255, 255, 255), "MUTED": (214, 228, 242), "ACCENT": (120, 206, 255),
        "GPU_C": (150, 236, 120), "RAM_C": (120, 180, 255), "OK": (120, 232, 120),
        "WARN": (255, 212, 80), "HOT": (255, 104, 96)}
ANALOG = {**DARK, "BG": (22, 20, 18), "PANEL": (44, 39, 34), "TRACK": (86, 76, 64),
          "TEXT": (246, 238, 222), "MUTED": (204, 190, 168), "ACCENT": (226, 176, 86),
          "GPU_C": (226, 126, 76), "RAM_C": (150, 192, 204), "OK": (156, 206, 112),
          "WARN": (242, 192, 72), "HOT": (236, 84, 62), "CLAUDE": (238, 152, 112)}
HUD = {**DARK, "BG": (0, 6, 2), "PANEL": (0, 22, 8), "TRACK": (22, 72, 36),
       "TEXT": (160, 255, 178), "MUTED": (104, 204, 124), "ACCENT": (120, 255, 150),
       "GPU_C": (96, 222, 255), "RAM_C": (206, 255, 120), "OK": (120, 255, 150),
       "WARN": (255, 204, 64), "HOT": (255, 84, 64), "CLAUDE": (255, 172, 112),
       "DISCORD": (150, 170, 255), "STEAM_BLUE": (110, 210, 255), "STEAM_GAME": (206, 255, 120)}
TRON = {**DARK, "BG": (0, 4, 10), "PANEL": (0, 16, 28), "TRACK": (0, 62, 86),
        "TEXT": (224, 250, 255), "MUTED": (140, 200, 220), "ACCENT": (0, 232, 255),
        "GPU_C": (255, 152, 32), "RAM_C": (124, 172, 255), "OK": (64, 255, 192),
        "WARN": (255, 212, 64), "HOT": (255, 72, 72), "CLAUDE": (255, 152, 92)}
PAPER = {**LIGHT, "BG": (240, 233, 216), "PANEL": (250, 246, 234), "TRACK": (196, 186, 166),
         "TEXT": (28, 26, 24), "MUTED": (84, 76, 66), "ACCENT": (26, 70, 140),
         "GPU_C": (120, 46, 140), "RAM_C": (30, 96, 170), "OK": (36, 110, 56),
         "WARN": (160, 100, 0), "HOT": (176, 28, 28), "CLAUDE": (180, 80, 40),
         "DISCORD": (70, 80, 200), "STEAM_BLUE": (20, 90, 150), "STEAM_GAME": (70, 120, 20)}
# Papier sombre : mêmes formes que le papier, encre crème sur papier charbon
PAPER_DARK = {**DARK, "BG": (30, 29, 32), "PANEL": (44, 42, 44), "TRACK": (92, 86, 80),
              "TEXT": (240, 234, 220), "MUTED": (190, 182, 168), "ACCENT": (130, 178, 236),
              "GPU_C": (204, 156, 232), "RAM_C": (120, 184, 240), "OK": (136, 210, 146),
              "WARN": (236, 194, 96), "HOT": (240, 112, 102), "CLAUDE": (238, 152, 112),
              "DISCORD": (150, 160, 255), "STEAM_BLUE": (110, 196, 245),
              "STEAM_GAME": (176, 220, 100)}
# Windows XP : corps de fenêtre beige, contrôles blancs à bord bleu-gris, barre de titre bleue
# (texte blanc dessus : HEAD_*), barres façon barre de progression, graphes du gestionnaire des
# tâches ; police Tahoma
XP = {**LIGHT, "BG": (236, 233, 216), "PANEL": (255, 255, 255), "TRACK": (198, 205, 214),
      "TEXT": (0, 0, 0), "MUTED": (72, 72, 72), "ACCENT": (0, 78, 210),
      "GPU_C": (150, 50, 160), "RAM_C": (0, 110, 200), "OK": (30, 150, 30),
      "WARN": (210, 130, 0), "HOT": (200, 20, 20), "CLAUDE": (196, 90, 50),
      "DISCORD": (70, 80, 210), "STEAM_BLUE": (0, 100, 170), "STEAM_GAME": (70, 130, 20),
      "HEAD_TEXT": (255, 255, 255), "HEAD_MUTED": (200, 220, 255),
      "HEAD_ACCENT": (255, 255, 255)}
# Nokia / Symbian (S60 des années 2007) : fond bleu nuit, barre du haut bleue vernie, panneaux
# bleus arrondis et brillants, sélection bleu vif ; police Trebuchet (proche de Nokia Sans)
SYMBIAN = {**DARK, "BG": (4, 20, 52), "PANEL": (16, 50, 104), "TRACK": (30, 62, 112),
           "TEXT": (255, 255, 255), "MUTED": (170, 196, 230), "ACCENT": (56, 170, 255),
           "GPU_C": (120, 210, 255), "RAM_C": (150, 230, 120), "OK": (110, 230, 90),
           "WARN": (255, 200, 60), "HOT": (255, 90, 80), "CLAUDE": (255, 160, 110),
           "DISCORD": (150, 160, 255), "STEAM_BLUE": (110, 200, 255),
           "STEAM_GAME": (170, 230, 90),
           "HEAD_TEXT": (255, 255, 255), "HEAD_MUTED": (190, 220, 255),
           "HEAD_ACCENT": (255, 255, 255)}
PIXEL = {**DARK, "BG": (12, 12, 28), "PANEL": (36, 36, 76), "TRACK": (76, 76, 124),
         "TEXT": (252, 252, 252), "MUTED": (188, 188, 204), "ACCENT": (60, 188, 252),
         "GPU_C": (248, 120, 88), "RAM_C": (184, 120, 248), "OK": (88, 216, 84),
         "WARN": (248, 184, 0), "HOT": (240, 40, 88), "CLAUDE": (252, 160, 68),
         "DISCORD": (104, 136, 252), "STEAM_BLUE": (60, 188, 252), "STEAM_GAME": (184, 248, 24)}
THEMES = {"dark": DARK, "light": LIGHT, "g19": G19, "g15": G15, "neon": NEON,
          "dynamic": DARK, "contrast": CONTRAST, "glacier": GLACIER, "braise": BRAISE,
          "terminal": TERMINAL, "red": NIGHT_RED, "aero": AERO, "analog": ANALOG, "hud": HUD,
          "tron": TRON, "paper": PAPER, "paper_dark": PAPER_DARK, "pixel": PIXEL, "xp": XP,
          "symbian": SYMBIAN}
THEME_LABELS = {"dark": "Sombre", "light": "Clair", "g19": "G19 (origine)",
                "g15": "Rétro G15", "neon": "Néon", "dynamic": "Dynamique (pochette)",
                "contrast": "Haut contraste", "glacier": "Glacier", "braise": "Braise",
                "terminal": "Terminal (phosphore)", "red": "Rouge nuit",
                "aero": "Aero (verre)", "analog": "Cadrans analogiques", "hud": "HUD cockpit",
                "tron": "Tron (vectoriel)", "paper": "Papier (encre)",
                "paper_dark": "Papier sombre", "pixel": "Pixel 8 bits",
                "xp": "Windows XP", "symbian": "Nokia / Symbian"}
_theme = "dark"
_backdrops = {}
HEAD_TEXT, HEAD_MUTED, HEAD_ACCENT = TEXT, MUTED, ACCENT   # texte sur la barre de titre


_dynamic = {"accent": None, "key": None}


def apply_theme(c):
    """Thème des réglages ; le thème dynamique prend en plus la couleur de la pochette en
    cours (ou du jeu lancé) comme accent, et en teinte légèrement les fonds."""
    global ANIMATE
    name = theme_of(c.settings)
    set_theme(name)
    ANIMATE = bool(c.settings.get("animations", True))
    _wall["on"] = bool(c.settings.get("wallpaper_bg"))
    _wall["dim"] = max(0, min(95, int(c.settings.get("wallpaper_dim", 60) or 0)))
    if name != "dynamic":
        return
    accent = _dynamic_accent(c)
    if accent == _dynamic["accent"]:
        return
    _dynamic["accent"] = accent
    base = DARK
    if accent is None:
        globals().update(base)
    else:
        globals().update({**base, "ACCENT": accent,
                          "BG": mix(base["BG"], accent, 0.05),
                          "PANEL": mix(base["PANEL"], accent, 0.10),
                          "TRACK": mix(base["TRACK"], accent, 0.18)})
    STATE_COLOR.update({"working": CLAUDE, "waiting": WARN, "idle": OK, "stale": MUTED})
    _backdrops.clear()
    _gloss_cache.clear()


_cover_accent = {}


def _dynamic_accent(c):
    m = c.media
    if m and m.title and m.accent:
        return _accent_for_dark(m.accent)
    s = c.games.session if c.games else None
    if s:
        if s.exe not in _cover_accent:
            cover = c.games.image(s, "cover")
            if cover is None:
                return None
            from .media import art_accent
            _cover_accent[s.exe] = art_accent(cover.convert("RGB"))
        rgb = _cover_accent[s.exe]
        return _accent_for_dark(rgb) if rgb else None
    return None


def _accent_for_dark(rgb):
    """Couleur (0..1) rendue lisible sur fond sombre (même règle que le lecteur)."""
    import colorsys
    h, l, s = colorsys.rgb_to_hls(*rgb)
    s = min(max(s, 0.55), 0.9)
    lo, hi = 0.32, 0.8
    l = min(l, 0.8)

    def lum(x):
        return _luminance(*colorsys.hls_to_rgb(h, x, s))

    if not lo <= lum(l) <= hi:
        target = hi if lum(l) > hi else lo
        a, b = (0.0, l) if lum(l) > hi else (l, 1.0)
        for _ in range(18):
            mid = (a + b) / 2
            a, b = (mid, b) if lum(mid) < target else (a, mid)
        l = (a + b) / 2
    r, g, b = colorsys.hls_to_rgb(h, l, s)
    return int(r * 255), int(g * 255), int(b * 255)


_g15_cache = {}


def postprocess(img):
    """Dernière passe selon le thème : écran monochrome ambre à trame de pixels (G15),
    phosphore vert à balayage (Terminal), tout en rouge (Rouge nuit), lueur autour des couleurs
    vives (Néon), lueur des traits (Tron, HUD), palette limitée (Pixel). Sans effet pour les
    autres thèmes."""
    if _theme in looks.SHAPED:
        shaped = looks.postprocess(img, _theme)
        if shaped is not None:
            return shaped
    if _theme == "g15":
        if "lut" not in _g15_cache:
            # 5 niveaux d'ambre, comme un LCD rétroéclairé ; trame de pixels 2×2
            levels = [(10, 6, 0), (48, 27, 0), (104, 60, 0), (200, 122, 0), (255, 194, 60)]
            cuts = (16, 52, 104, 172)        # fond | panneau | piste | secondaire | texte

            def level(v):
                return levels[sum(v >= c for c in cuts)]

            lut = [level(v) for v in range(256)]
            _g15_cache["lut"] = [c[0] for c in lut] + [c[1] for c in lut] + [c[2] for c in lut]
            grid = Image.new("L", (W, H), 0)
            gd = ImageDraw.Draw(grid)
            for y in range(1, H, 2):
                gd.line((0, y, W, y), fill=70)
            for x in range(1, W, 2):
                gd.line((x, 0, x, H), fill=40)
            _g15_cache["grid"] = grid
        gray = img.convert("L")
        out = Image.merge("RGB", (gray, gray, gray)).point(_g15_cache["lut"])
        out.paste((0, 0, 0), (0, 0), _g15_cache["grid"])
        return out
    if _theme in ("terminal", "red"):
        key = "lut_" + _theme
        if key not in _g15_cache:
            # tons moyens relevés (textes secondaires lisibles sur le LCD), noirs gardés
            lift = [255 * (v / 255) ** 0.7 if v > 20 else v for v in range(256)]
            if _theme == "terminal":
                # phosphore vert : noirs légèrement verts, blancs qui tirent vers le vert pâle
                tint = [(int(10 + u * 0.45 * (u / 255) ** 0.8), int(8 + u * 0.96),
                         int(5 + u * 0.42 * (u / 255) ** 1.4)) for u in lift]
            else:
                # rouge pur (la vision de nuit est préservée), noirs vraiment noirs
                tint = [(int(u), int(26 * (u / 255) ** 2), int(12 * (u / 255) ** 2))
                        for u in lift]
            _g15_cache[key] = [c[0] for c in tint] + [c[1] for c in tint] + [c[2] for c in tint]
            if _theme == "terminal":
                scan = Image.new("L", (W, H), 0)
                sd = ImageDraw.Draw(scan)
                for y in range(1, H, 2):
                    sd.line((0, y, W, y), fill=55)     # lignes de balayage, discrètes
                _g15_cache["scan"] = scan
        gray = img.convert("L")
        out = Image.merge("RGB", (gray, gray, gray)).point(_g15_cache[key])
        if _theme == "terminal":
            glow = out.point(lambda v: max(0, v - 90)).filter(ImageFilter.GaussianBlur(2.5))
            out = ImageChops.add(out, glow, scale=1.4)
            out.paste((0, 0, 0), (0, 0), _g15_cache["scan"])
        return out
    if _theme == "neon":
        bright = img.point(lambda v: max(0, v - 120) * 2)
        glow = bright.filter(ImageFilter.GaussianBlur(4))
        return ImageChops.add(img, glow, scale=1.6)
    return img


def theme_of(cfg):
    """Nom du thème des réglages (l'ancien réglage light_mode reste compris)."""
    name = cfg.get("theme") or ("light" if cfg.get("light_mode") else "dark")
    return name if name in THEMES else "dark"


def set_theme(name):
    """Bascule la palette de toutes les pages (voir THEMES)."""
    global _theme
    if isinstance(name, bool) or name is None:
        name = "light" if name else "dark"
    if name == _theme:
        return
    _theme = name
    palette = THEMES.get(name, DARK)
    globals().update(palette)
    globals().update(HEAD_TEXT=palette.get("HEAD_TEXT", palette["TEXT"]),
                     HEAD_MUTED=palette.get("HEAD_MUTED", palette["MUTED"]),
                     HEAD_ACCENT=palette.get("HEAD_ACCENT", palette["ACCENT"]))
    _dynamic["accent"] = "à recalculer"     # le thème dynamique repose son accent
    looks.clear()
    STATE_COLOR.update({"working": CLAUDE, "waiting": WARN, "idle": OK, "stale": MUTED})
    _backdrops.clear()


def backdrop(img):
    """Fond pleine page (pochette floutée, visuel de jeu) : éclairci en mode clair."""
    if not _light():
        return img
    hit = _backdrops.get(id(img))
    if not hit or hit[0] is not img:
        if len(_backdrops) > 16:
            _backdrops.clear()
        hit = _backdrops[id(img)] = (img, Image.blend(img, Image.new("RGB", img.size, BG), 0.75))
    return hit[1]


@dataclass
class Ctx:
    """Tout ce dont les pages ont besoin pour une image."""
    stats: object
    gpu: object
    sessions: list
    settings: dict
    media: object = None
    volume: object = None
    games: object = None
    discord: object = None
    notifs: object = None
    alerts: object = None
    speedtest: object = None
    weather: object = None
    vpn: object = None
    lyrics: object = None
    fans: object = None
    usage: object = None         # claude_usage.ClaudeUsage
    steam: object = None         # steam_live.SteamLive
    night: bool = False          # mode nuit en cours
    history: object = None       # history.History
    batteries: object = None     # battery.Batteries
    devices: object = None       # devices.DeviceWatcher
    net: object = None           # netping.Pinger
    sysw: object = None          # sysalerts.SystemWatch
    streaming: object = None     # streaming.Streaming (Sunshine / Parsec)
    docker: object = None        # docker_mon.DockerMonitor
    mirror: object = None        # screencap.ScreenMirror (page Écran PC)
    docker_scroll: int = 0
    fuel: object = None          # fuel.FuelMonitor : prix des carburants (Home Assistant)
    dnd: object = None           # dnd.DoNotDisturb : « Ne pas déranger » de Windows
    fuel_scroll: int = 0
    gpu_view: str = "both"       # page GPU en jeu : FPS et temps d'image, ou l'un des deux (OK)
    driver: object = None        # amd_driver.AmdDriver
    updater: object = None       # updater.Updater (mises à jour depuis GitHub)
    pages: list = None           # pages affichées (sans Discord / Docker fermés)
    discord_open: bool = True
    pages_hidden: set = None     # pages masquées faute d'appli lancée
    pages_event: tuple = None    # (titre, texte, horodatage, page) : une page masquée revient
    toast_closed: float = 0.0    # bandeaux arrivés avant : fermés (Annuler, ou OK pour y aller)
    toast_log: object = None     # deque des derniers bandeaux (page Bandeaux)
    toast_sel: int = 0
    claude_event: tuple = None   # (titre, texte, horodatage, session) : rappel d'une session
    agent_event: tuple = None    # (titre, texte, horodatage) : appli lancée par un agent Claude
    lgs_event: tuple = None      # (titre, texte, horodatage) : LGS bloque le rétroéclairage
    git: object = None           # git_status.GitStatus
    away: object = None          # away.Away (PC au repos, résumé d'absence)
    saved_event: tuple = None    # (titre, texte, horodatage) : réglages enregistrés ailleurs
    pulse_test: tuple = None     # (effet, fin) : pulsation montrée pour un test
    claude_sel: int = 0          # page Claude : session choisie (▲ ▼), OK la met au premier plan
    claude_sel_id: str = ""      # … retenue par son identifiant (la liste se retrie sans cesse)
    history_view: str = "temp"   # page Historique : "temp" ou "load" (bouton OK)
    steam_scroll: int = 0
    show_lyrics: bool = False    # page Média : paroles à la place du lecteur (bouton OK)
    audio_cursor: int = None     # page Audio : ligne en réglage (None = hors réglage)
    audio_pick: dict = None      # page Audio : périphérique en cours de choix {"out"|"in": i}
    claude_open: bool = True     # faux : voyant et encart Claude masqués
    scroll: int = 0
    media_key: tuple = None      # morceau en cours, pour le bandeau « changement de média »
    media_changed: float = 0


# polices par thème : (normale, grasse, échelle) ; Segoe UI pour les autres. Choisies parmi
# celles de Windows qui ont tous les caractères de l'appli (accents, °, flèches, ▲▼◄►, ●)
FONT_FACES = {"hud": ("CascadiaMono.ttf", "CascadiaMono.ttf", 0.86),    # chasse fixe
              "paper": ("times.ttf", "timesbd.ttf", 1.06),             # à empattements
              "paper_dark": ("times.ttf", "timesbd.ttf", 1.06),
              "xp": ("tahoma.ttf", "tahomabd.ttf", 1.0),
              "symbian": ("trebuc.ttf", "trebucbd.ttf", 1.0),       # proche de Nokia Sans
              "analog": ("framd.ttf", "framd.ttf", 1.0)}                # industrielle


def font(size, bold=False):
    return _font(_theme if _theme in FONT_FACES else "", size, bold)


@lru_cache(maxsize=None)
def _font(face, size, bold):
    regular, heavy, scale = FONT_FACES.get(face, ("segoeui.ttf", "segoeuib.ttf", 1.0))
    try:
        f = ImageFont.truetype(rf"C:\Windows\Fonts\{heavy if bold else regular}",
                               max(6, round(size * scale)))
        if face == "hud":         # police variable : graisse choisie par son nom
            f.set_variation_by_name("Bold" if bold else "Regular")
        return f
    except (OSError, ValueError):
        return ImageFont.load_default(size)


# Pixel 8 bits : textes sans lissage, nets comme sur une console
_draw_init = ImageDraw.ImageDraw.__init__


def _pixel_draw_init(self, im, mode=None):
    _draw_init(self, im, mode)
    if _theme == "pixel":
        self.fontmode = "1"


ImageDraw.ImageDraw.__init__ = _pixel_draw_init
textfx.install()


def _light():
    """Thème à fond clair (les fonds d'image sont éclaircis, les fondus inversés)."""
    return _theme in ("light", "paper", "xp")


# fond d'écran Windows derrière les pages (réglage, ou thème Aero) : voir apply_theme
_wall = {"on": False, "dim": 60}


def _wall_image():
    if not (_wall["on"] or _theme == "aero"):
        return None
    from . import wallpaper
    return wallpaper.image()


def _wall_canvas(wp):
    """Fond d'écran assombri (ou éclairci) vers le fond du thème, pour garder le texte lisible."""
    if _theme == "aero":
        target, f = (0, 0, 0), 0.48     # textes posés hors panneau : lisibles sur un fond clair
    else:
        # thème clair : fond d'écran davantage fondu, sinon les textes gris se perdent
        target, f = BG, (0.5 + _wall["dim"] / 200) if _light() else _wall["dim"] / 100
    key = ("wall", id(wp), target, f)
    hit = _canvas_cache.get(key)
    if hit is None or hit[0] is not wp:
        if len(_canvas_cache) > 24:
            _canvas_cache.clear()
        hit = _canvas_cache[key] = (wp, Image.blend(wp, Image.new("RGB", wp.size, target), f))
    return hit[1].copy()


# --- Helpers -----------------------------------------------------------------------------------

def load_color(pct, base):
    return HOT if pct >= 90 else WARN if pct >= 75 else base


_glides = {}
ANIMATE = True        # réglage « animations » (posé par apply_theme)


def glide(key, target, t, tau=0.07):
    """Valeur affichée qui rattrape `target` en douceur (constante de temps `tau` s) : curseurs
    qui glissent d'une ligne à l'autre, chiffres qui défilent. Saute directement à la cible au
    premier affichage, après une pause, ou animations coupées."""
    v, last = _glides.get(key, (target, None))
    if not ANIMATE or last is None or not 0 <= t - last < 0.5:
        v = target
    elif t > last:
        v += (target - v) * (1 - math.exp(-(t - last) / tau))
    if abs(target - v) < 0.05:
        v = target
    _glides[key] = (v, t)
    return v


def dim(c, f):
    return tuple(int(v * f + b * (1 - f)) for v, b in zip(c, BG))


def bar(d, x, y, w, h, frac, color, smooth=False):
    if _theme in looks.SHAPED and looks.bar(d, x, y, w, h, frac, color, _theme):
        return
    if _theme == "g19" and not smooth:
        return led_bar(d, x, y, w, h, frac, color)
    r = h // 2
    d.rounded_rectangle((x, y, x + w, y + h), r, fill=TRACK)
    fw = int(w * max(0.0, min(frac, 1.0)))
    if fw >= h:
        d.rounded_rectangle((x, y, x + fw, y + h), r, fill=color)
    elif fw > 0:
        d.ellipse((x, y, x + h, y + h), fill=color)
    if _theme == "g19" and h >= 4:
        # vernis : creux sombre en haut de la piste, reflet clair sur la moitié haute du plein
        d.line((x + r, y, x + w - r, y), fill=mix(TRACK, (0, 0, 0), 0.45))
        if fw >= h:
            for k in range(max(1, h // 2)):
                d.line((x + r, y + 1 + k, x + fw - r, y + 1 + k),
                       fill=mix(color, (255, 255, 255), 0.45 - 0.3 * k / max(1, h // 2)))
            d.line((x + r, y + h, x + fw - r, y + h), fill=mix(color, (0, 0, 0), 0.35))


def mix(a, b, f):
    """Mélange de deux couleurs (f = part de b)."""
    return tuple(int(u + (v - u) * f) for u, v in zip(a, b))


# --- thème G19 : graphiques façon oscilloscope, jauges à cadran chromé -------------------------

_grad_cache = {}


def _vgrad(w, h, top, bottom):
    key = (w, h, top, bottom)
    hit = _grad_cache.get(key)
    if hit is None:
        if len(_grad_cache) > 64:
            _grad_cache.clear()
        col = Image.new("RGB", (1, h))
        for yy in range(h):
            col.putpixel((0, yy), mix(top, bottom, yy / max(1, h - 1)))
        hit = _grad_cache[key] = col.resize((w, h))
    return hit


LED_OFF = (10, 14, 20)


def led_bar(d, x, y, w, h, frac, color):
    """Barre en segments de LED (allumés selon `frac`, le dernier plus vif), façon G-series."""
    x, y, w, h = int(x), int(y), int(w), int(h)
    seg = max(3, min(h, 6))
    n = max(1, (w + 1) // (seg + 1))
    lit = max(0.0, min(frac, 1.0)) * n
    off = mix(LED_OFF, color, 0.22)
    for k in range(n):
        sx = x + k * (seg + 1)
        if k < lit:
            c = mix(dim(color, 0.75), color, k / max(1, n - 1))
            if k + 1 >= lit:
                c = mix(c, (255, 255, 255), 0.35)   # tête de barre
            d.rectangle((sx, y, sx + seg - 1, y + h), fill=c)
            if h >= 4:
                d.line((sx, y, sx + seg - 1, y), fill=mix(c, (255, 255, 255), 0.35))
        else:
            d.rectangle((sx, y, sx + seg - 1, y + h), fill=off)


def led_graph(d, x, y, w, h, values, color, vmax=100):
    """Historique en matrice de LED : une colonne par mesure, cases allumées jusqu'à la valeur,
    la case du haut plus vive ; les cases éteintes dessinent la grille."""
    x, y, w, h = int(x), int(y), int(w), int(h)
    d.rectangle((x, y, x + w, y + h), fill=(3, 5, 8))
    cw, ch = 4, 3
    cols = (w - 1) // (cw + 1)
    rows = (h - 1) // (ch + 1)
    vals = list(values)[-cols:]
    vals = [None] * (cols - len(vals)) + vals       # alignées à droite (le plus récent à droite)
    off = mix((3, 5, 8), color, 0.18)
    x0 = x + 1 + (w - 1 - cols * (cw + 1)) // 2
    y0 = y + 1 + (h - 1 - rows * (ch + 1)) // 2
    for i, v in enumerate(vals):
        cx = x0 + i * (cw + 1)
        lit = 0 if v is None else max(1 if v > 0 else 0, round(min(v, vmax) / vmax * rows))
        for j in range(rows):          # j = 0 en bas
            cy = y0 + (rows - 1 - j) * (ch + 1)
            if j < lit:
                c = mix(dim(color, 0.65), color, j / max(1, rows - 1))
                if j == lit - 1:
                    c = mix(c, (255, 255, 255), 0.4)
            else:
                c = off
            d.rectangle((cx, cy, cx + cw - 1, cy + ch - 1), fill=c)


def dial(d, cx, cy, r, frac, color, value, unit, label):
    """Jauge à cadran : lunette chromée, graduations, arc en segments lumineux, centre vernis."""
    frac = max(0.0, min(frac, 1.0))
    img = getattr(d, "_image", None)
    # lunette chromée (claire en haut, sombre en bas)
    rb = r + 4
    if img is not None:
        ring = _vgrad(2 * rb + 1, 2 * rb + 1, (150, 156, 166), (28, 30, 34))
        m = Image.new("L", ring.size, 0)
        md = ImageDraw.Draw(m)
        md.ellipse((0, 0, 2 * rb, 2 * rb), fill=255)
        md.ellipse((3, 3, 2 * rb - 3, 2 * rb - 3), fill=0)
        img.paste(ring, (cx - rb, cy - rb), m)
    d.ellipse((cx - rb + 3, cy - rb + 3, cx + rb - 3, cy + rb - 3), fill=(6, 9, 13))
    # segments lumineux
    segs = 18
    box = (cx - r + 1, cy - r + 1, cx + r - 1, cy + r - 1)
    for k in range(segs):
        a0 = 135 + k * 270 / segs + 1.5
        a1 = a0 + 270 / segs - 3
        on = (k + 0.5) / segs <= frac
        d.arc(box, a0, a1, fill=color if on else mix((6, 9, 13), color, 0.16), width=5)
    # graduations
    for k in range(10):
        a = math.radians(135 + k * 30)
        r0, r1 = r - 9, r - 6
        d.line((cx + r0 * math.cos(a), cy + r0 * math.sin(a), cx + r1 * math.cos(a),
                cy + r1 * math.sin(a)), fill=(90, 96, 106))
    # reflet vitré sur la moitié haute
    d.chord((cx - r + 8, cy - r + 8, cx + r - 8, cy + r - 8), 200, 340,
            fill=mix((6, 9, 13), (255, 255, 255), 0.07))
    d.text((cx, cy - 2), value, font=font(16, True), fill=TEXT, anchor="mm")
    d.text((cx, cy + 13), unit, font=font(10), fill=MUTED, anchor="mm")
    d.text((cx, cy + r + 10), label, font=font(10), fill=MUTED, anchor="mm")


# --- thème G19 : panneaux vernis façon interface 2010 ------------------------------------------

_gloss_cache = {}


def _gloss(w, h, r, base):
    """Panneau brillant (dégradé, reflet sur la moitié haute, liseré) et son masque arrondi."""
    key = (w, h, r, base)
    hit = _gloss_cache.get(key)
    if hit:
        return hit
    if len(_gloss_cache) > 256:
        _gloss_cache.clear()
    top, bottom = mix(base, (255, 255, 255), 0.11), mix(base, (0, 0, 0), 0.45)
    col = Image.new("RGB", (1, h))
    split = max(1, h * 9 // 20)
    for y in range(h):
        if y < split:   # moitié haute : reflet nettement plus clair, coupé net (verre bombé)
            c = mix(mix(top, (255, 255, 255), 0.06), top, y / split)
        else:
            c = mix(base, bottom, (y - split) / max(1, h - split))
        col.putpixel((0, y), c)
    im = col.resize((w, h))
    dd = ImageDraw.Draw(im)
    dd.rounded_rectangle((0, 0, w - 1, h - 1), r, outline=mix(base, (0, 0, 0), 0.6))
    dd.line((r, 1, w - 1 - r, 1), fill=mix(top, (255, 255, 255), 0.35))  # arête lumineuse
    mask = Image.new("L", (w, h), 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, w - 1, h - 1), r, fill=255)
    _gloss_cache[key] = (im, mask)
    return im, mask


WALL_PANEL_ALPHA = 0.8    # fond d'écran affiché : opacité des panneaux (le fond transparaît)
WALL_BAR_ALPHA = 0.88


def _see_through(d, box, alpha, draw):
    """Dessine `draw()` (le panneau du thème, tel quel : vernis G19, hachures…) puis le rend
    un peu translucide sur le fond d'écran. Sans fond d'écran : dessin normal."""
    img = getattr(d, "_image", None)
    if img is None or img.mode not in ("RGB", "RGBA") or _wall_image() is None or \
            _theme in ("aero", "hud"):      # Aero : verre à lui ; HUD : déjà sans fond
        draw()
        return
    x0, y0, x1, y1 = (int(v) for v in box)
    b = (max(0, x0), max(0, y0), min(img.width, x1 + 1), min(img.height, y1 + 1))
    if b[2] - b[0] < 2 or b[3] - b[1] < 2:
        draw()
        return
    before = img.crop(b)
    draw()
    img.paste(Image.blend(before, img.crop(b), alpha), b[:2])


def panel(d, box, r, outline=None, width=1, color=None):
    """Fond de carte : uni dans les thèmes sombre et clair, vernis dans le thème G19."""
    color = color or PANEL
    _see_through(d, box, WALL_PANEL_ALPHA, lambda: _panel(d, box, r, outline, width, color))


def _panel(d, box, r, outline, width, color):
    if _theme in looks.SHAPED and looks.panel(d, box, r, outline, width, color, _theme):
        return
    x0, y0, x1, y1 = (int(v) for v in box)
    img = getattr(d, "_image", None)
    if _theme != "g19" or img is None or x1 - x0 < 4 or y1 - y0 < 4:
        d.rounded_rectangle(box, r, fill=color, outline=outline, width=width)
        return
    im, mask = _gloss(x1 - x0 + 1, y1 - y0 + 1, r, color)
    img.paste(im, (x0, y0), mask)
    if outline:
        d.rounded_rectangle(box, r, outline=outline, width=width)


def title_bar(d):
    """Bandeau du haut : uni, chromé (G19), liseré dégradé magenta → cyan (Néon)."""
    _see_through(d, (0, 0, W, 24), WALL_BAR_ALPHA, lambda: _title_bar(d))


def _title_bar(d):
    if _theme in looks.SHAPED and looks.title_bar(d, _theme):
        return
    if _theme == "neon":
        d.rectangle((0, 0, W, 24), fill=mix(BG, PANEL, 0.6))
        for x in range(W):
            d.point((x, 24), fill=mix(GPU_C, ACCENT, x / W))
        return
    if _theme in ("g15", "dynamic"):
        d.rectangle((0, 0, W, 24), fill=PANEL)
        d.line((0, 24, W, 24), fill=ACCENT)
        return
    if _theme != "g19":
        d.rectangle((0, 0, W, 24), fill=PANEL)
        return
    for y in range(24):
        if y < 11:      # chrome : reflet clair coupé net au milieu
            c = mix((112, 118, 128), (74, 79, 88), y / 11)
        else:
            c = mix((44, 48, 55), (18, 20, 24), (y - 11) / 13)
        d.line((0, y, W, y), fill=c)
    d.line((0, 0, W, 0), fill=(150, 156, 166))
    d.line((0, 24, W, 24), fill=ACCENT)


_canvas_cache = {}


def canvas():
    """Image de fond d'une page : unie, ou en dégradé (G19 : bleu nuit, Néon : violet)."""
    wp = _wall_image()
    if wp is not None:
        return _wall_canvas(wp)
    if _theme in looks.SHAPED:
        shaped = looks.canvas(_theme)
        if shaped is not None:
            return shaped
    if _theme == "neon":
        if "neon" not in _canvas_cache:
            col = Image.new("RGB", (1, H))
            for y in range(H):
                col.putpixel((0, y), mix((28, 6, 48), (6, 2, 14), y / H))
            _canvas_cache["neon"] = col.resize((W, H))
        return _canvas_cache["neon"].copy()
    if _theme != "g19":
        return Image.new("RGB", (W, H), BG)
    if "g19" not in _canvas_cache:
        col = Image.new("RGB", (1, H))
        for y in range(H):
            col.putpixel((0, y), mix((14, 20, 30), (0, 0, 0), y / H))
        _canvas_cache["g19"] = col.resize((W, H))
    return _canvas_cache["g19"].copy()


def sparkline(d, x, y, w, h, values, color, vmax=100, panel="auto"):
    if _theme in looks.SHAPED and looks.sparkline(d, x, y, w, h, values, color, vmax,
                                                   PANEL if panel == "auto" else panel, _theme):
        return
    if _theme == "g19":
        return led_graph(d, x, y, w, h, values, color, vmax)
    panel = PANEL if panel == "auto" else panel
    if panel:
        d.rounded_rectangle((x, y, x + w, y + h), 4, fill=panel)
    vals = list(values)
    n = len(vals)
    if n < 2:
        return
    pts = [(x + i * w / (n - 1), y + h - 2 - (h - 4) * min(v, vmax) / vmax) for i, v in enumerate(vals)]
    d.polygon([(x, y + h)] + pts + [(x + w, y + h)], fill=dim(color, 0.3))
    d.line(pts, fill=color, width=2)


def fmt_bytes(n, suffix=""):
    for unit in ("o", "Ko", "Mo", "Go", "To"):
        if abs(n) < 1024 or unit == "To":
            return f"{n:.0f} {unit}{suffix}" if unit in ("o", "Ko") else f"{n:.1f} {unit}{suffix}"
        n /= 1024


def fmt_age(s):
    if s < 60:
        return f"{int(s)} s"
    if s < 3600:
        return f"{int(s // 60)} min"
    return f"{int(s // 3600)} h"


def fit(d, text, fnt, maxw):
    # une seule ligne : un message sur plusieurs lignes (Discord…) est remis bout à bout
    text = " ".join(str(text or "").split())
    if d.textlength(text, font=fnt) <= maxw:
        return text
    lo, hi = 0, len(text)  # plus long préfixe qui tient avec « … » (recherche dichotomique)
    while lo < hi:
        mid = (lo + hi + 1) // 2
        if d.textlength(text[:mid] + "…", font=fnt) <= maxw:
            lo = mid
        else:
            hi = mid - 1
    return text[:lo].rstrip() + "…"


def state_dot(d, cx, cy, state, t, r=4):
    color = STATE_COLOR.get(state, MUTED)
    if state == "waiting":  # clignote
        color = color if (t * 2) % 2 < 1.3 else dim(color, 0.25)
    elif state == "working":  # pulse
        r = r + 1.2 * math.sin(t * 5)
    d.ellipse((cx - r, cy - r, cx + r, cy + r), fill=color)


# --- Bandeau supérieur avec le voyant Claude ---------------------------------------------------

# rayons de l'étoile Claude : (angle en degrés, longueur relative), irréguliers comme le logo
CLAUDE_RAYS = [(0, 1.0), (31, 0.82), (62, 0.95), (93, 0.78), (122, 1.0), (152, 0.86),
               (183, 0.97), (213, 0.8), (243, 0.93), (274, 0.84), (304, 1.0), (334, 0.79)]


@lru_cache(maxsize=64)
def _claude_star(size, color, step):
    """Étoile Claude lissée (dessinée 4× plus grande puis réduite), tournée de `step`°."""
    k = 4
    n = size * k
    im = Image.new("RGBA", (n, n), (0, 0, 0, 0))
    dd = ImageDraw.Draw(im)
    c = n / 2
    for ang, length in CLAUDE_RAYS:
        a = math.radians(ang + step)
        ca, sa = math.cos(a), math.sin(a)
        r0, r1 = n * 0.06, n * 0.5 * length
        w0, w1 = n * 0.075, n * 0.035     # rayon plus large au centre, fin au bout
        px, py = -sa, ca
        dd.polygon([(c + ca * r0 + px * w0, c + sa * r0 + py * w0),
                    (c + ca * r1 + px * w1, c + sa * r1 + py * w1),
                    (c + ca * r1 - px * w1, c + sa * r1 - py * w1),
                    (c + ca * r0 - px * w0, c + sa * r0 - py * w0)], fill=color)
    dd.ellipse((c - n * 0.1, c - n * 0.1, c + n * 0.1, c + n * 0.1), fill=color)
    return im.resize((size, size), Image.LANCZOS)


def claude_icon(d, cx, cy, size, color, spin=0.0):
    """Logo Claude (étoile orange) à la place du mot « Claude » ; `spin` en degrés."""
    img = getattr(d, "_image", None)
    if img is None:
        return
    star = _claude_star(size, tuple(color[:3]), int(spin) % 30)   # 12 rayons : périodique
    x, y = int(round(cx - size / 2)), int(round(cy - size / 2))
    if img.mode == "RGBA":
        img.alpha_composite(star, (x, y))
    else:
        img.paste(star, (x, y), star)


def header(d, index, count, sessions, t, discord=None, alerts=None, title="", done_s=0,
           streaming=None, headset=None):
    title_bar(d)
    lt = time.localtime(t)
    d.text((8, 12), time.strftime("%H:%M", lt), font=font(17, True), fill=HEAD_TEXT, anchor="lm")
    d.line((60, 6, 60, 18), fill=TRACK, width=1)
    # nom de la page (la date en plus sur la page Système), puis sa position « 3/11 »
    label = title or f"{JOURS[lt.tm_wday]} {lt.tm_mday}"
    d.text((67, 12), label, font=font(12, True), fill=HEAD_ACCENT, anchor="lm")
    x = 67 + d.textlength(label, font=font(12, True)) + 6
    if count > 1:
        d.text((x, 13), f"{index + 1}/{count}", font=font(9), fill=HEAD_MUTED, anchor="lm")
        x += d.textlength(f"{index + 1}/{count}", font=font(9))
    left_end = x + 6        # fin du titre : les icônes de droite ne doivent pas l'atteindre

    # voyant Claude : un point + compteur par état, de droite à gauche (masqué si `sessions`
    # vaut None, c.-à-d. Claude fermé). Un agent fini passe au repos (gris) après done_s.
    x = W - 8
    counts = {}
    for s in sessions or []:
        if s.state == "idle" and 0 < done_s <= s.age:
            continue
        counts[s.state] = counts.get(s.state, 0) + 1
    shown = [st for st in ("idle", "working", "waiting") if counts.get(st)]
    if sessions is None:
        pass
    elif not shown:
        claude_icon(d, x - 7, 12, 15, HEAD_MUTED)   # au repos : étoile grise (claire sur le bleu XP)
        x -= 14
    else:
        # un nombre par état, dans sa couleur, sans pastille : la couleur suffit
        for st in shown:
            n = str(counts[st])
            d.text((x, 12), n, font=font(13, True), fill=STATE_COLOR[st], anchor="rm")
            x -= d.textlength(n, font=font(13, True)) + 5
        x -= 2
        # étoile de la couleur de l'état le plus urgent : jaune (attend, clignote), orange
        # (travaille, tourne), vert (a fini)
        top = shown[-1]
        color = STATE_COLOR[top]
        if top == "waiting" and (t * 2) % 2 >= 1.3:
            color = dim(color, 0.35)
        claude_icon(d, x - 6, 12, 15, color, t * 40 if top == "working" else 0)
        x -= 14

    # badge Discord : bulle avec le nombre de messages non lus ; en vocal, un casque (vert),
    # micro barré si muet, casque barré si en sourdine
    # état micro / casque dès que Discord est ouvert, vert en vocal, gris hors vocal
    dc_on = bool(discord and (discord.voice or discord.status == "connecté"))
    if discord and (discord.unread or dc_on):
        x -= 8
        if discord.unread:
            n = str(min(discord.unread, 99))
            w = d.textlength(n, font=font(11, True)) + 12
            d.rounded_rectangle((x - w, 4, x, 18), 6, fill=DISCORD)
            d.polygon([(x - w + 4, 17), (x - w + 4, 22), (x - w + 9, 17)], fill=DISCORD)
            d.text((x - w / 2, 11), n, font=font(11, True), fill=(255, 255, 255), anchor="mm")
            x -= w + 6
        if dc_on:
            deaf, mute = discord.self_deaf, discord.self_mute
            # casque rouge seulement en sourdine ; en muet, seul le micro barré est rouge
            headset_icon(d, x - 9, 12, HOT if deaf else OK if discord.voice else dim(TEXT, 0.7))
            if deaf:
                d.line((x - 17, 4, x - 1, 20), fill=HOT, width=2)
            x -= 22
            if mute and not deaf:
                mic_icon(d, x - 13, 12, True, HOT)   # micro barré, bien à gauche du casque
                x -= 18

    # casque HyperX : micro (barré en rouge quand le bouton du casque le coupe) et batterie
    if headset is not None and headset.connected:
        if headset.mic_muted is not None:
            x -= 6
            if headset.mic_muted:
                mic_icon(d, x - 12, 12, True, HOT)
            else:
                mic_icon(d, x - 12, 12, False, dim(HEAD_TEXT, 0.7))
            x -= 16
        if headset.level is not None and x - 50 > left_end:   # place pour « 92 » + la pile
            lvl = headset.level
            charging = headset.charging in (1, 2)
            color = OK if charging or lvl > 50 else WARN if lvl > 20 else HOT
            x -= 4
            # petite pile : contour, téton, remplissage selon le niveau
            d.rounded_rectangle((x - 17, 8, x - 3, 16), 2, outline=dim(HEAD_TEXT, 0.8), width=1)
            d.rectangle((x - 2, 10, x - 1, 14), fill=dim(HEAD_TEXT, 0.8))
            fw = int(11 * max(0, min(lvl, 100)) / 100)
            if fw > 0:
                d.rectangle((x - 15, 10, x - 15 + fw, 14), fill=color)
            label = f"{lvl}" + ("+" if charging else "")
            d.text((x - 20, 12), label, font=font(10, True),
                   fill=color if lvl <= 20 and not charging else HEAD_TEXT, anchor="rm")
            x -= 22 + d.textlength(label, font=font(10, True))

    if alerts and alerts.active:
        x -= 8
        on = (t * 2) % 2 < 1.4
        w = 24 + (10 if len(alerts.active) > 1 else 0)
        d.rounded_rectangle((x - w, 5, x, 19), 7, fill=HOT if on else dim(HOT, 0.4))
        d.polygon([(x - w + 12, 7), (x - w + 6, 17), (x - w + 18, 17)], fill=TEXT)
        d.text((x - w + 12, 13), "!", font=font(8, True), fill=HOT, anchor="mm")
        if len(alerts.active) > 1:
            d.text((x - 6, 12), str(len(alerts.active)), font=font(10, True), fill=TEXT,
                   anchor="rm")
        x -= w

    # quelqu'un regarde ce PC en streaming (Sunshine / Parsec) : écran rouge « à l'antenne »
    if streaming and streaming.active:
        x -= 8
        col = mix(HOT, BG, 0.35 * (0.5 + 0.5 * math.sin(t * 4)))
        d.rounded_rectangle((x - 18, 5, x, 17), 2, outline=col, width=2)
        d.line((x - 9, 17, x - 9, 20), fill=col, width=2)
        d.line((x - 13, 20, x - 5, 20), fill=col, width=2)
        d.ellipse((x - 12, 8, x - 6, 14), fill=col)


# --- Pages -------------------------------------------------------------------------------------

def with_temp(name, temp):
    return f"{name}  ·  {temp:.0f}°C" if temp else name


def fan_icon(d, cx, cy, r, angle, color):
    """Petite hélice à trois pales (angle en degrés, pour l'animer)."""
    for k in range(3):
        a = angle + k * 120
        d.pieslice((cx - r, cy - r, cx + r, cy + r), a, a + 55, fill=color)
    d.ellipse((cx - r * 0.3, cy - r * 0.3, cx + r * 0.3, cy + r * 0.3), fill=color)


def page_system(d, st, gpu, sessions, t, media=None, fans=None):
    # CPU
    y = 30
    c = load_color(st.cpu, ACCENT)
    d.text((10, y), "CPU", font=font(13, True), fill=c)
    name = with_temp(st.cpu_name, gpu.s.get("cpu_temp"))
    d.text((44, y + 2), name, font=font(11), fill=MUTED)
    pct = f"{st.cpu:.0f}%"
    d.text((310, y - 3), pct, font=font(20, True), fill=TEXT, anchor="ra")
    if fans and fans.readings:
        # rappel discret dans le vide de la ligne CPU : touche OK + hélice (tourne au rythme
        # du ventilo CPU) = panneau des ventilateurs
        x = 44 + d.textlength(name, font=font(11)) + 10
        room = 310 - d.textlength(pct, font=font(20, True)) - 8
        mode = dict(FAN_CHIPS).get(fans.applied, "")
        safety = getattr(fans, "safety", None)
        if safety:
            mode = "Auto · chaud"          # sécurité : le profil choisi reviendra refroidi
        if x + 34 < room:
            rpm = next((f["rpm"] for f in fans.readings if f["name"] == "CPU Fan"), 1200)
            cy = y + 9
            d.rounded_rectangle((x, cy - 6, x + 19, cy + 6), 3, outline=dim(ACCENT, 0.7))
            d.text((x + 10, cy), "OK", font=font(8, True), fill=ACCENT, anchor="mm")
            fan_icon(d, x + 29, cy, 5, (t * rpm / 8) % 360, ACCENT)
            # mode de ventilation en cours, s'il tient avant le pourcentage
            if mode and x + 38 + d.textlength(mode, font=font(9, True)) < room:
                d.text((x + 38, cy), mode, font=font(9, True), fill=WARN if safety else MUTED,
                       anchor="lm")
    sparkline(d, 10, y + 22, 300, 30, st.cpu_hist, c)

    # GPU + VRAM
    y = 88
    load = gpu.s.get("load", st.gpu)
    c = load_color(load, GPU_C)
    d.text((10, y), "GPU", font=font(13, True), fill=c)
    d.text((44, y + 2), with_temp(st.gpu_name, gpu.s.get("temp")), font=font(11), fill=MUTED)
    d.text((310, y - 3), f"{load:.0f}%", font=font(20, True), fill=TEXT, anchor="ra")
    bar(d, 10, y + 22, 300, 7, load / 100, c)
    vram = st.vram_used / st.vram_total if st.vram_total else 0
    d.text((10, y + 33), "VRAM", font=font(11), fill=MUTED)
    d.text((310, y + 33), f"{fmt_bytes(st.vram_used)} / {fmt_bytes(st.vram_total)}",
           font=font(11), fill=TEXT, anchor="ra")
    bar(d, 50, y + 39, 150, 4, vram, dim(GPU_C, 0.7))

    # RAM
    y = 142
    ram = st.ram
    c = load_color(ram.percent, RAM_C)
    d.text((10, y), "RAM", font=font(13, True), fill=c)
    ram_pct = ram.percent
    d.text((310, y + 1), f"{fmt_bytes(ram.used)} / {fmt_bytes(ram.total)}  ·  {ram_pct:.0f}%",
           font=font(12), fill=TEXT, anchor="ra")
    bar(d, 10, y + 20, 300, 7, ram_pct / 100, c)

    # Réseau + disques
    y = 174
    f = font(12)
    d.text((10, y), "↓", font=font(12, True), fill=OK)
    d.text((22, y), fmt_bytes(st.net_down, "/s"), font=f, fill=TEXT)
    d.text((90, y), "↑", font=font(12, True), fill=ACCENT)
    d.text((102, y), fmt_bytes(st.net_up, "/s"), font=f, fill=TEXT)
    d.text((10, y + 15), "disque", font=font(11), fill=MUTED)
    d.text((50, y + 15), f"L {fmt_bytes(st.disk_read, '/s')}  É {fmt_bytes(st.disk_write, '/s')}",
           font=font(11), fill=MUTED)
    x = 178
    for mount, pct in st.disks[:3]:
        d.text((x, y), mount.rstrip(":"), font=font(11, True), fill=TEXT)
        bar(d, x, y + 18, 36, 5, pct / 100, load_color(pct, MUTED))
        d.text((x + 36, y + 1), f"{pct:.0f}%", font=font(10), fill=MUTED, anchor="ra")
        x += 46


    if sessions is None:
        info_strip(d, st, media)
    else:
        claude_strip(d, sessions, t)


def claude_active(sessions, cfg):
    """L'encart Claude de la page système a-t-il lieu d'être ? Oui si un agent travaille ou
    attend, ou a fini il y a moins de claude_strip_seconds ; sinon la place va au média."""
    delay = cfg.get("claude_strip_seconds", 10)
    if delay <= 0:
        return True
    return any(s.state in ("working", "waiting") or s.age < delay for s in sessions or [])


def info_strip(d, st, media):
    """Encart du bas quand Claude est fermé : média en cours, sinon depuis quand le PC tourne."""
    y0, y1 = 212, 236
    cy = (y0 + y1) // 2
    panel(d, (6, y0, W - 6, y1), 6)
    if media and media.title:
        d.rounded_rectangle((6, y0, 10, y1), 2, fill=CLAUDE if media.playing else MUTED)
        play_icon(d, 22, cy, not media.playing, CLAUDE if media.playing else MUTED)
        line = media.title + (f" — {media.artist}" if media.artist else "")
        d.text((36, cy), fit(d, line, font(12), W - 52), font=font(12), fill=TEXT, anchor="lm")
        return
    up = st.uptime
    d.text((16, cy), f"Allumé depuis {int(up // 86400)} j {int(up % 86400 // 3600)} h "
                     f"{int(up % 3600 // 60):02d} min", font=font(12), fill=MUTED, anchor="lm")
    d.text((W - 14, cy), f"{len(psutil.pids())} processus", font=font(11), fill=MUTED, anchor="rm")


def claude_strip(d, sessions, t):
    """Encart Claude en bas de la page système : la session la plus importante."""
    y0, y1 = 212, 236
    panel(d, (6, y0, W - 6, y1), 6)
    cy = (y0 + y1) // 2
    if not sessions:
        d.ellipse((16, cy - 4, 24, cy + 4), outline=MUTED, width=1)
        d.text((32, cy), "Claude · aucune session", font=font(12), fill=MUTED, anchor="lm")
        return
    s = sessions[0]
    color = STATE_COLOR.get(s.state, MUTED)
    d.rounded_rectangle((6, y0, 10, y1), 2, fill=color)
    state_dot(d, 20, cy, s.state, t)
    x = 32
    name = fit(d, s.name, font(13, True), 110)
    d.text((x, cy), name, font=font(13, True), fill=TEXT, anchor="lm")
    x += d.textlength(name, font=font(13, True)) + 8
    detail = STATE_LABEL.get(s.state, s.state)
    if s.state == "working" and s.tool:
        detail = s.tool
    elif s.state == "waiting" and s.message:
        detail = s.message
    right = f"+{len(sessions) - 1}" if len(sessions) > 1 else fmt_age(s.age)
    rw = d.textlength(right, font=font(11)) + 12
    d.text((x, cy), fit(d, detail, font(12), W - 6 - rw - x), font=font(12), fill=color, anchor="lm")
    d.text((W - 14, cy), right, font=font(11), fill=MUTED, anchor="rm")


CLAUDE_ROWS = 5


def fmt_tokens(n):
    if n >= 1e6:
        return f"{n / 1e6:.1f} M".replace(".", ",")
    return f"{n / 1e3:.0f} k" if n >= 1000 else str(n)


def usage_strip(d, usage, t):
    """Bas de la page Claude : usage du bloc de 5 h en cours et des 7 derniers jours,
    compté depuis les transcripts locaux."""
    y0, y1 = 212, 236
    cy = (y0 + y1) // 2
    panel(d, (6, y0, W - 6, y1), 6)
    if not usage or not usage.ready:
        d.text((16, cy), "Usage · calcul…", font=font(11), fill=MUTED, anchor="lm")
        return
    d.text((14, cy), "5 h", font=font(10, True), fill=CLAUDE, anchor="lm")
    if usage.block_reset:
        left = max(0, usage.block_reset - t)
        x = 38
        main = fmt_tokens(usage.block_tokens)
        d.text((x, cy), main, font=font(12, True), fill=TEXT, anchor="lm")
        x += d.textlength(main, font=font(12, True)) + 6
        d.text((x, cy), f"· {usage.block_messages} rép. · reset {time.strftime('%H:%M', time.localtime(usage.block_reset))}"
               f" ({int(left // 3600)} h {int(left % 3600 // 60):02d})",
               font=font(10), fill=MUTED, anchor="lm")
    else:
        d.text((38, cy), "aucun bloc en cours", font=font(11), fill=MUTED, anchor="lm")
    d.text((W - 14, cy), f"7 j {fmt_tokens(usage.week_tokens)}", font=font(10, True), fill=MUTED,
           anchor="rm")


def git_chip(d, x, y, g, max_x):
    """Après le nom de la session : branche, fichiers modifiés, commits à pousser / tirer."""
    parts = [(g["branch"], dim(ACCENT, 0.9), True)]
    dirty = g["changed"] + g["untracked"]
    if dirty:
        parts.append((f"●{dirty}", WARN, True))
    if g["ahead"]:
        parts.append((f"↑{g['ahead']}", TEXT, False))
    if g["behind"]:
        parts.append((f"↓{g['behind']}", TEXT, False))
    for i, (text, color, bold) in enumerate(parts):
        f = font(10, bold)
        if i == 0:
            text = fit(d, text, f, max(0, max_x - x - 40))
        w = d.textlength(text, font=f)
        if x + w > max_x:
            return
        d.text((x, y), text, font=f, fill=color, anchor="lm")
        x += w + 5


PR_LOOK = {"ok": ("CI ok", "OK"), "fail": ("CI échec", "HOT"), "running": ("CI en cours", "WARN")}


def pr_label(pr):
    """(texte, couleur) de la PR de la branche, None s'il n'y en a pas."""
    if not pr or not pr.get("number"):
        return None
    text = f"PR #{pr['number']}"
    if pr["state"] == "merged":
        return text + " fusionnée", MUTED
    if pr["state"] == "closed":
        return text + " fermée", MUTED
    if pr.get("draft"):
        text += " brouillon"
    look = PR_LOOK.get(pr.get("ci"))
    if look:
        return f"{text} · {look[0]}", globals()[look[1]]
    return text, TEXT


def page_claude(d, sessions, t, scroll=0, usage=None, sel=0, git=None):
    usage_strip(d, usage, t)
    if not sessions:
        d.text((W // 2, 100), "Aucune session Claude", font=font(16, True), fill=MUTED, anchor="mm")
        d.text((W // 2, 124), "les hooks s'activent au prochain lancement",
               font=font(11), fill=dim(MUTED, 0.7), anchor="mm")
        key_hints(d, 160, [("OK", "ouvrir Claude")], "center", color=CLAUDE)
        return
    rows = sessions[scroll:scroll + CLAUDE_ROWS]
    if len(sessions) <= CLAUDE_ROWS - 1:
        key_hints(d, 200, [("▲▼", "choisir"), ("OK", "aller à la session")], "right",
                  color=CLAUDE)
    for i, s in enumerate(rows):
        y = 30 + i * 35
        color = STATE_COLOR.get(s.state, MUTED)
        panel(d, (6, y, W - 6, y + 31), 6)
        d.rounded_rectangle((6, y, 10, y + 31), 2, fill=color)
        state_dot(d, 22, y + 10, s.state, t)
        age = fmt_age(s.age)
        d.text((W - 14, y + 10), age, font=font(11), fill=MUTED, anchor="rm")
        right = W - 22 - d.textlength(age, font=font(11))
        if s.context:
            # contexte de l'agent, en milliers de jetons
            ctx = f"ctx {s.context / 1000:.0f}k"
            d.text((right, y + 10), ctx, font=font(10, True), fill=dim(ACCENT, 0.85), anchor="rm")
            right -= d.textlength(ctx, font=font(10, True)) + 8
        g = git.get(s.cwd) if git else None
        name = fit(d, s.name, font(13, True), 110 if g else 160)
        d.text((34, y + 10), name, font=font(13, True), fill=TEXT, anchor="lm")
        if g:
            git_chip(d, 40 + d.textlength(name, font=font(13, True)), y + 10, g, right)
        label = STATE_LABEL.get(s.state, s.state)
        detail = s.message if s.state == "waiting" else s.tool if s.state == "working" else ""
        line = f"{label} · {detail}" if detail else label
        pr = pr_label(g.get("pr")) if g else None
        room = W - 50
        if pr:
            d.text((W - 14, y + 23), pr[0], font=font(10, True), fill=pr[1], anchor="rm")
            room -= d.textlength(pr[0], font=font(10, True)) + 10
        d.text((34, y + 23), fit(d, line, font(11), room), font=font(11), fill=color, anchor="lm")
    if len(sessions) > CLAUDE_ROWS:
        d.text((W - 8, 208), f"{scroll + 1}-{scroll + len(rows)}/{len(sessions)}",
               font=font(9), fill=MUTED, anchor="rb")
    if len(sessions) > 1 and scroll <= sel < scroll + len(rows):
        cy = glide("claude_cursor", 30 + (sel - scroll) * 35, t)
        d.rounded_rectangle((6, cy, W - 6, cy + 31), 6, outline=ACCENT, width=1)

def page_cores(d, st, t, sensors=None):
    cores = st.cores or [0]
    n = len(cores)
    top, bottom = 34, 196
    slot = 300 / n
    for i, v in enumerate(cores):
        x = 10 + i * slot
        bw = max(slot - 3, 2)
        panel(d, (x, top, x + bw, bottom), 2)
        h = (bottom - top) * min(v, 100) / 100
        if h >= 1:
            d.rounded_rectangle((x, bottom - h, x + bw, bottom), 2, fill=load_color(v, ACCENT))
        if n <= 32 and (i % 2 == 0 or n <= 16):
            d.text((x + bw / 2, bottom + 4), str(i), font=font(9), fill=MUTED, anchor="mt")
    d.text((10, 220), f"{n} threads · moy. {st.cpu:.0f}% · max {max(cores):.0f}%",
           font=font(12), fill=TEXT, anchor="lm")
    s = sensors or {}
    x = 310
    for text, color in ((f"{s['cpu_clock'] / 1000:.1f} GHz", MUTED) if s.get("cpu_clock") else (None, None),
                        (f"{s['cpu_temp']:.0f}°C", temp_color(s["cpu_temp"])) if s.get("cpu_temp")
                        else (None, None)):
        if text:
            d.text((x, 220), text, font=font(13 if "°" in text else 11, True), fill=color,
                   anchor="rm")
            x -= d.textlength(text, font=font(13 if "°" in text else 11, True)) + 8


def temp_color(v):
    return HOT if v >= 90 else WARN if v >= 75 else OK


def gauge(d, cx, cy, r, frac, color, value, unit, label):
    if _theme in looks.SHAPED and looks.gauge(d, cx, cy, r, frac, color, value, unit, label,
                                               _theme):
        return
    if _theme == "g19":
        return dial(d, cx, cy, r, frac, color, value, unit, label)
    box = (cx - r, cy - r, cx + r, cy + r)
    d.arc(box, 135, 405, fill=TRACK, width=6)
    frac = max(0.0, min(frac, 1.0))
    if frac > 0.005:
        d.arc(box, 135, 135 + 270 * frac, fill=color, width=6)
    d.text((cx, cy - 2), value, font=font(16, True), fill=TEXT, anchor="mm")
    d.text((cx, cy + 13), unit, font=font(10), fill=MUTED, anchor="mm")
    d.text((cx, cy + r + 4), label, font=font(11), fill=MUTED, anchor="mm")


def num(v, fmt="{:.0f}", suffix=""):
    return "—" if v is None else fmt.format(v) + suffix


def frametime_graph(d, x, y, w, h, values, median):
    """Temps d'image en barres, le plus récent à droite : plus haut = image plus lente ;
    orange au-delà de 1,5× la médiane, rouge pour une saccade (> 2× et +8 ms)."""
    vals = list(values)[-int(w):]
    vmax = max(median * 3, 20.0)
    base = y + h
    mid = base - h * min(median, vmax) / vmax
    for px in range(int(x), int(x + w), 4):            # médiane en pointillés
        d.line((px, mid, px + 1, mid), fill=dim(MUTED, 0.6))
    step = w / max(len(vals), 1)
    for i, v in enumerate(vals):
        bh = max(1, h * min(v, vmax) / vmax)
        spike = v > 2 * median and v - median > 8
        color = HOT if spike else WARN if v > 1.5 * median else ACCENT
        x0 = x + w - (len(vals) - i) * step
        d.rectangle((x0, base - bh, x0 + max(step - 1, 0), base), fill=color)


GPU_VIEWS = ("both", "fps", "frametime")   # graphe en jeu, OK passe au suivant


def page_gpu(d, st, gpu, t, power_max=315, view="both"):
    s = gpu.s
    game = gpu.game

    # FPS
    panel(d, (6, 28, 112, 92), 6)
    if game:
        fps = game["fps"]
        d.text((59, 36), "FPS", font=font(10, True), fill=MUTED, anchor="mt")
        d.text((59, 60), f"{fps:.0f}", font=font(30, True),
               fill=HOT if fps < 30 else WARN if fps < 55 else TEXT, anchor="mm")
        d.text((59, 84), f"{game['frametime_ms']:.1f} ms", font=font(11), fill=MUTED, anchor="mb")
    else:
        d.text((59, 52), "—", font=font(24, True), fill=MUTED, anchor="mm")
        d.text((59, 80), "aucun jeu", font=font(11), fill=MUTED, anchor="mm")

    # graphe : FPS en jeu, sinon charge GPU
    panel(d, (118, 28, 314, 92), 6)
    stats = gpu.fps_stats() if game else None
    if stats:
        d.text((126, 32), fit(d, game["name"].rsplit(".", 1)[0], font(11, True), 110),
               font=font(11, True), fill=TEXT)
        d.text((308, 32), f"1% {stats['low1']:.0f}", font=font(10), fill=MUTED, anchor="ra")
        ft = gpu.ft_stats() if hasattr(gpu, "ft_stats") else None
        # échelle resserrée autour des valeurs vues (pas depuis 0) : les chutes se voient même
        # sur un graphe bas
        lo = stats["min"] * 0.8
        fps_vals = [v - lo for v in gpu.fps_hist]
        fps_max = max(stats["max"] * 1.05 - lo, 5)
        if ft and view == "both":
            # FPS en haut, temps d'image en bas ; unités à droite
            sparkline(d, 124, 45, 168, 14, fps_vals, ACCENT, vmax=fps_max, panel=None)
            frametime_graph(d, 124, 62, 168, 13, gpu.ft_hist, ft["median"])
            d.text((309, 52), "fps", font=font(9), fill=MUTED, anchor="rm")
            d.text((309, 69), "ms", font=font(9), fill=MUTED, anchor="rm")
        elif ft and view == "frametime":
            frametime_graph(d, 124, 47, 184, 27, gpu.ft_hist, ft["median"])
        if ft and view in ("both", "frametime"):
            spikes = ft["spikes"]
            line = (f"moy {stats['avg']:.0f} fps · {ft['median']:.1f} ms · "
                    + (f"{spikes} saccade{'s' if spikes > 1 else ''}" if spikes else "fluide"))
            d.text((213, 88), line.replace(".", ","), font=font(10), fill=WARN if spikes > 3
                   else MUTED, anchor="mb")
        else:
            sparkline(d, 124, 48, 184, 30, fps_vals, ACCENT, vmax=fps_max, panel=None)
            d.text((213, 88), f"min {stats['min']:.0f} · moy {stats['avg']:.0f} · max {stats['max']:.0f}",
                   font=font(10), fill=MUTED, anchor="mb")
    else:
        d.text((126, 32), "Charge GPU", font=font(11, True), fill=TEXT)
        d.text((308, 32), " + ".join(gpu.sources) or "PDH", font=font(10), fill=MUTED, anchor="ra")
        sparkline(d, 124, 50, 184, 36, gpu.load_hist, GPU_C, panel=None)

    # jauges
    load = s.get("load", 0.0)
    temp = s.get("temp")
    power = s.get("power")
    gauge(d, 56, 126, 25, load / 100, load_color(load, GPU_C), f"{load:.0f}", "%", "Charge")
    gauge(d, 160, 126, 25, (temp or 0) / 110, temp_color(temp or 0), num(temp), "°C", "Température")
    gauge(d, 264, 126, 25, (power or 0) / power_max, load_color((power or 0) / power_max * 100,
          ACCENT), num(power), "W", "Puissance")

    # détails
    vram = s.get("vram_mb")
    fan = num(s.get("fan_rpm"), suffix=" tr/min")
    if s.get("fan_pct") is not None:
        fan += f" · {s['fan_pct']:.0f}%"
    cpu = num(s.get("cpu_temp"), suffix="°") + f" · {st.cpu:.0f}%"
    if s.get("cpu_clock"):
        cpu += f" · {s['cpu_clock'] / 1000:.1f} GHz"
    hot = s.get("hotspot")
    rows = [
        [("Core", num(s.get("core_clock"), suffix=" MHz")),
         ("Ventilo", fan)],
        [("Mémoire", num(s.get("mem_clock"), suffix=" MHz")),
         ("VRAM", (f"{vram / 1024:.1f}" if vram is not None else "—")
          + f" / {st.vram_total / 2**30:.0f} Go")],
        [("Hotspot", num(hot, suffix=f"°  (max {gpu.temp_max:.0f}°)" if hot else "°")),
         ("CPU", cpu)],
        [("VRAM temp.", num(s.get("mem_temp"), suffix="°")),
         ("Tension", num(s.get("voltage"), "{:.3f}", " V")) if s.get("voltage")
         else ("CPU puiss.", num(s.get("cpu_power"), suffix=" W"))],
    ]
    for i, row in enumerate(rows):
        y = 176 + i * 16
        for j, (label, value) in enumerate(row):
            x0, x1 = (8, 154) if j == 0 else (166, 312)
            d.text((x0, y), label, font=font(11), fill=MUTED, anchor="lm")
            color = temp_color(hot) if label == "Hotspot" and hot else TEXT
            room = x1 - x0 - d.textlength(label, font=font(11)) - 6
            d.text((x1, y), fit(d, value, font(11, True), room), font=font(11, True), fill=color,
                   anchor="rm")
    d.line((160, 170, 160, 232), fill=TRACK)


def fmt_time(sec):
    sec = int(sec)
    return f"{sec // 3600}:{sec // 60 % 60:02d}:{sec % 60:02d}" if sec >= 3600 else f"{sec // 60}:{sec % 60:02d}"


def shrink_line(d, text, maxw, sizes):
    """Une ligne : la plus grande taille de `sizes` où elle tient, sinon la plus petite et
    raccourcie avec « … »."""
    text = " ".join(str(text or "").split())
    for size in sizes:
        if d.textlength(text, font=font(size)) <= maxw:
            return text, size
    return fit(d, text, font(sizes[-1]), maxw), sizes[-1]


def fit_block(d, text, maxw, sizes, max_lines, bold=False):
    """Coupe `text` en au plus `max_lines` lignes à la plus grande taille possible, sans
    « … » tant que la plus petite taille suffit. Renvoie (lignes, taille)."""
    text = " ".join(str(text or "").split())
    for size in sizes:
        fnt = font(size, bold)
        words, lines = text.split(), []
        while words:
            cur = words.pop(0)
            while words and d.textlength(f"{cur} {words[0]}", font=fnt) <= maxw:
                cur += " " + words.pop(0)
            lines.append(cur)
        if len(lines) <= max_lines and all(d.textlength(l, font=fnt) <= maxw for l in lines):
            return lines, size
    size = sizes[-1]
    return wrap(d, text, font(size, bold), maxw, max_lines), size


def wrap(d, text, fnt, maxw, lines):
    """Coupe `text` en au plus `lines` lignes, avec « … » si ça déborde."""
    words = text.split()
    out = []
    while words and len(out) < lines:
        cur = words.pop(0)
        while words and d.textlength(f"{cur} {words[0]}", font=fnt) <= maxw:
            cur += " " + words.pop(0)
        out.append(cur)
    if words:
        out[-1] = fit(d, out[-1] + " " + " ".join(words), fnt, maxw)
    return [fit(d, line, fnt, maxw) for line in out]


def play_icon(d, cx, cy, playing, color):
    if playing:  # pause
        d.rounded_rectangle((cx - 6, cy - 7, cx - 2, cy + 7), 1, fill=color)
        d.rounded_rectangle((cx + 2, cy - 7, cx + 6, cy + 7), 1, fill=color)
    else:
        d.polygon([(cx - 5, cy - 8), (cx - 5, cy + 8), (cx + 8, cy)], fill=color)


def skip_icon(d, cx, cy, forward, color):
    s = 1 if forward else -1
    d.polygon([(cx - 6 * s, cy - 6), (cx - 6 * s, cy + 6), (cx + 2 * s, cy)], fill=color)
    xa, xb = sorted((cx + 3 * s, cx + 5 * s))
    d.rectangle((xa, cy - 6, xb, cy + 6), fill=color)




def speaker_icon(d, x, cy, muted, color):
    d.rectangle((x, cy - 3, x + 3, cy + 3), fill=color)
    d.polygon([(x + 3, cy - 3), (x + 8, cy - 7), (x + 8, cy + 7), (x + 3, cy + 3)], fill=color)
    if muted:
        d.line((x + 11, cy - 4, x + 17, cy + 4), fill=HOT, width=2)
        d.line((x + 11, cy + 4, x + 17, cy - 4), fill=HOT, width=2)
    else:
        d.arc((x + 6, cy - 5, x + 14, cy + 5), -50, 50, fill=color, width=2)


def headset_icon(d, cx, cy, color):
    """Casque : arceau et deux écouteurs."""
    d.arc((cx - 7, cy - 8, cx + 7, cy + 6), 180, 360, fill=color, width=2)
    d.rounded_rectangle((cx - 8, cy - 1, cx - 4, cy + 6), 2, fill=color)
    d.rounded_rectangle((cx + 4, cy - 1, cx + 8, cy + 6), 2, fill=color)


def mic_icon(d, x, cy, muted, color):
    d.rounded_rectangle((x + 3, cy - 7, x + 8, cy + 2), 2, fill=color)
    d.arc((x, cy - 4, x + 11, cy + 5), 0, 180, fill=color, width=1)
    d.line((x + 5, cy + 5, x + 5, cy + 7), fill=color)
    if muted:
        d.line((x, cy - 7, x + 11, cy + 7), fill=HOT, width=2)


def level_bar(d, x, y, w, level, peak, muted, color, h=6):
    """Barre de volume avec le vumètre en direct par-dessus (plus clair)."""
    level = max(0.0, min(level or 0.0, 1.0))
    bar(d, x, y, w, h, 0 if muted else level, color)
    if not muted and level and peak > 0.01:
        fill = w * level
        if _theme == "g19":       # LED : le vumètre s'arrête au dernier segment allumé
            seg = max(3, min(h, 6))
            n = max(1, (w + 1) // (seg + 1))
            fill = max(0, math.ceil(level * n) * (seg + 1) - 1)
        pw = int(fill * min(peak * 1.4, 1.0))
        if pw >= h:
            d.rounded_rectangle((x, y + h // 2 - 1, x + pw, y + h // 2 + 1), 1,
                                fill=mix(color, (255, 255, 255), 0.55))


def history_graph(d, x, y, w, h, vals, color, vmax):
    """Historique en colonnes (une par tranche de temps, vides sans mesure) ; matrice de LED
    dans le thème G19."""
    if _theme == "g19":
        return led_graph(d, x, y, w, h, vals, color, vmax)
    panel(d, (x, y, x + w, y + h), 4)
    n = len(vals)
    cw = w / n
    for k in (1, 2, 3):
        gy = y + h * k // 4
        d.line((x + 2, gy, x + w - 2, gy), fill=mix(PANEL, TRACK, 0.5))
    for i, v in enumerate(vals):
        if v is None:
            continue
        top = y + h - 2 - (h - 4) * min(v, vmax) / vmax
        x0 = x + i * cw
        d.rectangle((x0 + 0.5, top, x0 + cw - 0.5, y + h - 2), fill=dim(color, 0.55))
        d.line((x0 + 0.5, top, x0 + cw - 0.5, top), fill=color)


def page_history(d, c, t):
    """Les dernières 24 h : températures ou charges CPU et GPU (OK pour basculer)."""
    h = c.history
    view = c.history_view
    keys = ("cpu_t", "gpu_t") if view == "temp" else ("cpu", "gpu")
    colors = (ACCENT, GPU_C)
    s = c.gpu.s if c.gpu else {}
    current = {"cpu_t": s.get("cpu_temp"), "gpu_t": s.get("temp"),
               "cpu": c.stats.cpu if c.stats else None, "gpu": s.get("load")}
    from .history import METRICS
    if not h or len(h.points) < 2:
        empty_state(d, ICON_HISTORY, "Historique des 24 dernières heures",
                    "une mesure par minute, les courbes se remplissent")
        return
    for k, (key, color) in enumerate(zip(keys, colors)):
        y = 30 + k * 94
        label, unit, _ = METRICS[key]
        cur = current.get(key)
        d.text((10, y + 6), label, font=font(13, True), fill=color, anchor="lm")
        d.text((48, y + 7), "—" if cur is None else f"{cur:.0f}{unit}", font=font(12, True),
               fill=TEXT, anchor="lm")
        info = []
        pk = h.peak(key) if h else None
        if pk:
            info.append(f"max {pk[0]:.0f}{unit} à {time.strftime('%H:%M', time.localtime(pk[1]))}")
        mean = h.mean(key) if h else None
        if mean is not None:
            info.append(f"moy. {mean:.0f}{unit}")
        d.text((W - 10, y + 7), " · ".join(info), font=font(10), fill=MUTED, anchor="rm")
        vals = h.series(key, 74, t) if h else [None] * 74
        history_graph(d, 10, y + 16, 300, 66, vals, color, 100)
    for x, lab, anchor in ((10, "-24 h", "la"), (W // 2, "-12 h", "ma"), (W - 10, "maint.", "ra")):
        d.text((x, 208), lab, font=font(9), fill=MUTED, anchor=anchor)
    other = "charges" if view == "temp" else "températures"
    key_hints(d, 228, [("OK", other)], "right")


def ping_color(ms):
    return MUTED if ms is None else OK if ms < 50 else WARN if ms < 100 else HOT


def page_network(d, c, t):
    """Réseau en jeu : ping en direct, statistiques de la dernière minute, graphe des 2 min."""
    p = c.net
    if not p:
        return
    st = p.stats(60)
    last = st.get("last")
    color = ping_color(last)
    d.text((12, 34), "PING", font=font(9, True), fill=ACCENT)
    d.text((12, 48), "perdu" if last is None and st["count"] else
           "—" if last is None else f"{last:.0f}", font=font(36, True), fill=color)
    if last is not None:
        d.text((12 + d.textlength(f"{last:.0f}", font=font(36, True)) + 4, 78), "ms",
               font=font(12, True), fill=MUTED, anchor="ls")
    rows = [("moyenne", st.get("avg"), " ms"), ("min / max", None, ""),
            ("gigue", st.get("jitter"), " ms"), ("perte", st["loss"], " %")]
    x0, x1 = 150, W - 12
    for i, (label, v, unit) in enumerate(rows):
        y = 38 + i * 15
        d.text((x0, y), label, font=font(10), fill=MUTED, anchor="lm")
        if label == "min / max":
            text = f"{st['min']:.0f} / {st['max']:.0f} ms" if "min" in st else "—"
        else:
            text = "—" if v is None else f"{v:.0f}{unit}" if unit != " %" else f"{v:.0f} %"
        warn = (label == "perte" and st["loss"] > 0) or (label == "gigue" and (v or 0) > 15)
        d.text((x1, y), text, font=font(11, True), fill=WARN if warn else TEXT, anchor="rm")
    # graphe des 2 dernières minutes (une colonne par seconde, ou par paire de secondes)
    samples = list(p.samples)
    vmax = max(100.0, max((v for v in samples if v is not None), default=0) * 1.2)
    gy, gh = 104, 84
    if _theme == "g19":
        cols = (300 - 1) // 5
        vals = samples[-cols:]
        led_graph(d, 10, gy, 300, gh, vals, color if last is not None else ACCENT, vmax)
        vals = [None] * (cols - len(vals)) + vals
        x0g = 10 + 1 + (300 - 1 - cols * 5) // 2
        for i, v in enumerate(vals):
            if v is None and i >= cols - len(samples):
                d.rectangle((x0g + i * 5, gy + gh - 5, x0g + i * 5 + 3, gy + gh - 2), fill=HOT)
    else:
        vals = samples[-100:]
        vals = [None] * (100 - len(vals)) + vals
        history_graph(d, 10, gy, 300, gh, vals, ACCENT, vmax)
        cw = 300 / 100
        for i, v in enumerate(vals):
            if v is None and i >= 100 - len(samples):
                d.rectangle((10 + i * cw, gy + gh - 6, 10 + i * cw + cw - 0.5, gy + gh - 2),
                            fill=HOT)
    d.text((10, gy + gh + 4), "-2 min", font=font(9), fill=MUTED)
    d.text((W - 10, gy + gh + 4), "maint.", font=font(9), fill=MUTED, anchor="ra")
    d.text((W // 2, gy + gh + 4), f"échelle {vmax:.0f} ms", font=font(9), fill=MUTED, anchor="ma")
    target = p.status or f"cible {p.target} · un ping par seconde"
    game = c.gpu.game if c.gpu else None
    d.text((10, 232), fit(d, target, font(9), 200), font=font(9), fill=MUTED, anchor="lb")
    d.text((W - 10, 232), "en jeu : alertes actives" if game else "alertes pendant les jeux",
           font=font(9, bool(game)), fill=OK if game else dim(MUTED, 0.8), anchor="rb")


def battery_icon(d, x, cy, w, h, level, color, connected=True):
    """Pile horizontale remplie selon le niveau."""
    d.rounded_rectangle((x, cy - h // 2, x + w, cy + h // 2), 3, outline=TEXT if connected
                        else MUTED, width=2)
    d.rectangle((x + w + 1, cy - h // 5, x + w + 3, cy + h // 5), fill=TEXT if connected else MUTED)
    fw = int((w - 6) * max(0, min(level, 100)) / 100)
    if fw > 0:
        d.rectangle((x + 3, cy - h // 2 + 3, x + 3 + fw, cy + h // 2 - 3), fill=color)


DOCKER_ROWS = 5
DOCKER_STATE = {"running": ("en marche", "OK"), "restarting": ("redémarre", "HOT"),
                "paused": ("en pause", "WARN"), "exited": ("arrêté", "MUTED"),
                "created": ("créé", "MUTED"), "dead": ("mort", "HOT")}


def page_docker(d, c, t):
    """Conteneurs Docker : état, CPU, RAM ; ceux qui tournent en premier."""
    dk = c.docker
    items = dk.containers if dk else []
    if not items:
        msg = (dk.status if dk and dk.status else "Aucun conteneur")
        empty_state(d, ICON_BOX, "Docker", msg)
        return
    run = [x for x in items if x["state"] == "running"]
    cpu = sum(x["cpu"] for x in run)
    mem = sum(x["mem"] for x in run)
    d.text((10, 36), f"{len(run)}/{len(items)} en marche", font=font(12, True), fill=TEXT,
           anchor="lm")
    d.text((W - 10, 36), f"CPU {cpu:.0f}% · RAM {fmt_bytes(mem)}", font=font(11), fill=MUTED,
           anchor="rm")
    c.docker_scroll = max(0, min(c.docker_scroll, len(items) - DOCKER_ROWS))
    img = d._image
    smooth_rows(img, "docker_scroll", c.docker_scroll, len(items), 48, 48 + DOCKER_ROWS * 37,
                37, lambda li, ld, idx, y: _docker_row(ld, items[idx], y), t)
    if len(items) > DOCKER_ROWS:
        first, last = c.docker_scroll + 1, min(len(items), c.docker_scroll + DOCKER_ROWS)
        d.text((W - 8, 238), f"{first}-{last}/{len(items)} · ▲▼", font=font(9), fill=MUTED,
               anchor="rb")


def _docker_row(d, x, y):
    """Une ligne de conteneur (y : haut de la ligne)."""
    label, col = DOCKER_STATE.get(x["state"], (x["state"], "MUTED"))
    col = globals()[col]
    if x.get("oom"):
        label, col = "arrêté · mémoire (OOM)", HOT
    elif x["state"] == "exited" and x["exit"] not in (0, 130, 137, 143):
        label, col = f"arrêté · code {x['exit']}", HOT
    panel(d, (6, y, W - 6, y + 33), 6)
    d.rounded_rectangle((6, y, 9, y + 33), 2, fill=col)
    on = x["state"] == "running"
    d.text((16, y + 10), fit(d, x["name"], font(12, True), 150), font=font(12, True),
           fill=TEXT if on else MUTED, anchor="lm")
    sub = label + (f" · {x['restarts']} redém." if x["restarts"] else "")
    d.text((16, y + 24), fit(d, f"{sub} · {x['image']}", font(9), 160), font=font(9),
           fill=col, anchor="lm")
    if on:
        bar = 56
        frac = min(x["cpu"], 100) / 100
        d.text((W - 14 - bar - 6, y + 10), f"{x['cpu']:.0f}%", font=font(11, True),
               fill=load_color(x["cpu"], TEXT), anchor="rm")
        d.rounded_rectangle((W - 14 - bar, y + 7, W - 14, y + 13), 3, fill=TRACK)
        if frac > 0.01:
            d.rounded_rectangle((W - 14 - bar, y + 7, W - 14 - bar + bar * frac, y + 13), 3,
                                fill=load_color(x["cpu"], ACCENT))
        memf = x["mem"] / x["mem_limit"] if x["mem_limit"] else 0
        d.text((W - 14 - bar - 6, y + 24), fmt_bytes(x["mem"]), font=font(10), fill=MUTED,
               anchor="rm")
        d.rounded_rectangle((W - 14 - bar, y + 21, W - 14, y + 27), 3, fill=TRACK)
        if memf > 0.01:
            d.rounded_rectangle((W - 14 - bar, y + 21, W - 14 - bar + bar * min(memf, 1),
                                 y + 27), 3, fill=load_color(memf * 100, GPU_C))


FUEL_ROWS = 5


def page_fuel(d, c, t):
    """Prix des carburants des stations suivies dans Home Assistant : le moins cher en tête,
    puis un tableau station × carburant (moins cher en vert, rupture en rouge)."""
    from .fuel import cheapest, fmt_price, fuels_of

    fm = c.fuel
    stations = fm.stations if fm else {}
    if not stations:
        msg = fm.status if fm and fm.status else "Aucune station"
        empty_state(d, ICON_CAR, "Carburant",
                    "Home Assistant à configurer : utilitaire → Services"
                    if fm and fm.status == "Home Assistant non configuré" else msg)
        return
    fuels = fuels_of(stations)
    main = c.settings.get("fuel_main") or ""
    if main not in fuels:   # carburant vendu par le plus de stations
        main = max(fuels, key=lambda f: sum(f in s["fuels"] for s in stations.values()))

    # en tête : le moins cher pour le carburant principal
    best = cheapest(stations, main)
    panel(d, (6, 28, W - 6, 66), 6)
    d.text((14, 38), f"{main.upper()} LE MOINS CHER", font=font(9, True), fill=ACCENT,
           anchor="lm")
    if best:
        price = fmt_price(best[0])
        d.text((14, 55), fit(d, best[1]["short"], font(13, True), 170), font=font(13, True),
               fill=TEXT, anchor="lm")
        d.text((W - 32, 49), price, font=font(22, True), fill=OK, anchor="rm")
        d.text((W - 14, 52), "€/l", font=font(9), fill=MUTED, anchor="rm")
    else:
        d.text((14, 55), "en rupture partout", font=font(12, True), fill=HOT, anchor="lm")

    # tableau : une ligne par station, une colonne par carburant
    x0 = 104
    col = (W - 8 - x0) / len(fuels)
    cell = font(11 if len(fuels) <= 5 else 10, True)
    y = 76
    for k, f in enumerate(fuels):
        cx = x0 + col * (k + 0.5)
        d.text((cx, y), f, font=font(9, True), fill=ACCENT if f == main else MUTED, anchor="mm")
    lows = {f: (cheapest(stations, f) or (None,))[0] for f in fuels}
    rows = list(stations.values())
    c.fuel_scroll = max(0, min(c.fuel_scroll, len(rows) - FUEL_ROWS))
    def station_row(li, d, idx, y):
        i, s = idx, rows[idx]
        if i % 2 == 0:
            panel(d, (6, y, W - 6, y + 26), 5)
        name, city = s["short"], s["city"]
        if city and name.casefold().endswith(" " + city.casefold()):
            name = name[:-len(city)].strip()     # « Intermarché JOINVILLE » : ville dessous
        d.text((12, y + 9), fit(d, name, font(11, True), x0 - 16), font=font(11, True),
               fill=TEXT, anchor="lm")
        if city and city.casefold() not in name.casefold():
            d.text((12, y + 20), fit(d, city.title(), font(8), x0 - 16), font=font(8),
                   fill=MUTED, anchor="lm")
        for k, f in enumerate(fuels):
            cx = x0 + col * (k + 0.5)
            v = s["fuels"].get(f)
            if not v:
                d.text((cx, y + 13), "–", font=font(10), fill=dim(MUTED, 0.6), anchor="mm")
            elif v["out"]:
                d.text((cx, y + 13), "rupture", font=font(8, True), fill=HOT, anchor="mm")
            else:
                stale = v["age"] is not None and v["age"] >= 4   # prix pas relevé depuis 4 j
                low = lows[f] is not None and v["price"] <= lows[f] + 1e-9
                color = OK if low else (dim(TEXT, 0.55) if stale else TEXT)
                d.text((cx, y + 13), fmt_price(v["price"]), font=cell, fill=color, anchor="mm")

    smooth_rows(d._image, "fuel_scroll", c.fuel_scroll, len(rows), 86, 86 + FUEL_ROWS * 28, 28,
                station_row, t)

    # pied : fraîcheur des prix et état de la lecture
    ages = [v["age"] for s in rows for v in s["fuels"].values() if v["age"] is not None]
    foot = f"prix relevés {fmt_ago(min(ages) * 86400)}" if ages else ""
    if any(a >= 4 for a in ages):
        foot += " · en gris : pas relevé depuis 4 j"
    if fm.status:
        foot, color = fm.status, WARN
    else:
        color = dim(MUTED, 0.85)
    span = ""
    if len(rows) > FUEL_ROWS:
        span = f"{c.fuel_scroll + 1}-{min(len(rows), c.fuel_scroll + FUEL_ROWS)}/{len(rows)} · ▲▼"
        d.text((W - 8, 236), span, font=font(9), fill=MUTED, anchor="rb")
    room = W - 20 - (int(d.textlength(span, font=font(9))) + 8 if span else 0)
    d.text((10, 236), fit(d, foot, font(9), room), font=font(9), fill=color, anchor="lb")


TOAST_ROWS = 6


def page_toasts(img, d, c, t):
    """Les 20 derniers bandeaux, le plus récent en haut ; ▲ ▼ choisir, OK ouvrir."""
    log = list(c.toast_log or ())
    d.text((10, 36), "Derniers bandeaux", font=font(12, True), fill=TEXT, anchor="lm")
    if not log:
        empty_state(d, ICON_MESSAGE, "Aucun bandeau pour l'instant",
                    "messages, amis, alertes… les 20 derniers restent ici")
        return
    c.toast_sel = max(0, min(c.toast_sel, len(log) - 1))
    top = max(0, min(c.toast_sel - TOAST_ROWS + 2, len(log) - TOAST_ROWS))
    top = min(top, c.toast_sel)
    d.text((W - 10, 36), f"{c.toast_sel + 1}/{len(log)}", font=font(9), fill=MUTED, anchor="rm")
    cache = c.discord.avatars if c.discord else None
    for i, n in enumerate(log[top:top + TOAST_ROWS]):
        y = 48 + i * 31
        color = n.get("color") or ACCENT
        if isinstance(color, list):
            color = tuple(color)
        panel(d, (6, y, W - 6, y + 28), 5)
        d.rounded_rectangle((6, y, 9, y + 28), 2, fill=color)
        avatar(img, d, cache, n.get("icon"), 26, y + 14, 20, n.get("title") or n.get("source"),
               color=color)
        when = time.strftime("%H:%M", time.localtime(n["at"]))
        d.text((W - 12, y + 8), when, font=font(9), fill=MUTED, anchor="rm")
        sw = d.textlength(when, font=font(9)) + 8
        src = fit(d, n.get("source") or "", font(8, True), 90)
        d.text((W - 12 - sw, y + 8), src, font=font(8, True), fill=color, anchor="rm")
        sw += d.textlength(src, font=font(8, True)) + 6
        d.text((42, y + 8), fit(d, n.get("title") or "", font(11, True), W - 54 - sw),
               font=font(11, True), fill=TEXT, anchor="lm")
        d.text((42, y + 21), fit(d, n.get("body") or "", font(10), W - 54), font=font(10),
               fill=dim(TEXT, 0.75), anchor="lm")
    cy = glide("toasts_cursor", 48 + (c.toast_sel - top) * 31, t)
    d.rounded_rectangle((6, cy, W - 6, cy + 28), 5, outline=ACCENT, width=1)
    key_hints(d, 230, [("▲▼", "choisir"), ("OK", "ouvrir")])


def page_screen(img, d, c, t):
    """Recopie en direct d'un écran du PC ; OK change d'écran, ▲ ▼ zoom autour du curseur."""
    m = c.mirror
    if not m:
        return
    m.want()
    frame = m.frame
    if frame is None:
        empty_state(d, ICON_SCREEN, "Recopie de l'écran", m.status or "démarrage de la capture…")
        return
    x0 = (W - frame.width) // 2
    y0 = 25 + (215 - frame.height) // 2
    img.paste(frame, (x0, y0))
    if m.cursor:   # la capture Windows n'inclut pas le curseur : petit repère à sa place
        cx, cy = x0 + m.cursor[0], y0 + m.cursor[1]
        d.polygon([(cx, cy), (cx, cy + 10), (cx + 3, cy + 7), (cx + 7, cy + 7)],
                  fill=(255, 255, 255), outline=(0, 0, 0))
    if y0 + frame.height < H - 12:
        d.text((10, H - 8), m.label, font=font(9), fill=MUTED, anchor="lm")
        key_hints(d, H - 8, [("OK", "écran"), ("▲▼", "zoom")], "right")


def page_batteries(d, c, t):
    """Batterie des appareils Bluetooth connus de Windows et du casque HyperX (dongle)."""
    from .battery import LOW
    b = c.batteries
    devices = b.devices if b else []
    if not devices:
        msg = (b.status if b and b.status else "Aucun appareil avec batterie")
        empty_state(d, ICON_BATTERY, "Batteries", msg)
        return
    for i, dev in enumerate(devices[:5]):
        y = 30 + i * 40
        lvl = dev["level"]
        color = HOT if lvl <= LOW else WARN if lvl <= 50 else OK
        if not dev["connected"]:
            color = MUTED
        panel(d, (6, y, W - 6, y + 36), 6)
        battery_icon(d, 14, y + 18, 34, 18, lvl, color, dev["connected"])
        d.text((60, y + 11), fit(d, dev["name"], font(13, True), 170), font=font(13, True),
               fill=TEXT if dev["connected"] else MUTED, anchor="lm")
        state = ("en charge" if dev.get("charging") else "connecté") if dev["connected"] \
            else "éteint · dernier niveau connu"
        d.text((60, y + 26), state, font=font(9), fill=OK if dev["connected"] else MUTED,
               anchor="lm")
        d.text((W - 14, y + 18), f"{lvl} %", font=font(18, True),
               fill=color if dev["connected"] else MUTED, anchor="rm")
    d.text((10, 232), f"alerte sous {LOW} % · relu chaque minute", font=font(9),
           fill=dim(MUTED, 0.8), anchor="lb")


_thumb_cache = {}


def _thumb(path, w, h):
    """Vignette d'une image locale (bannière Steam…), mise en cache."""
    key = (str(path), w, h)
    if key not in _thumb_cache:
        if len(_thumb_cache) > 32:
            _thumb_cache.clear()
        try:
            from PIL import ImageOps
            with Image.open(path) as im:
                _thumb_cache[key] = ImageOps.fit(im.convert("RGB"), (w, h), Image.LANCZOS)
        except (OSError, ValueError):
            _thumb_cache[key] = None
    return _thumb_cache[key]


def fmt_size(n):
    return f"{n / 2**30:.1f} Go".replace(".", ",") if n >= 2**30 else f"{n / 2**20:.0f} Mo"


FRIENDS_VISIBLE = 5


def page_steam(img, d, c, t):
    """Steam : téléchargements / mises à jour en cours, puis amis en ligne."""
    sl = c.steam
    if not sl or not sl.root:
        d.text((W // 2, 120), "Steam introuvable", font=font(16, True), fill=MUTED, anchor="mm")
        return
    lib = getattr(c.games, "steam", None) if c.games else None
    y = 30
    d.text((10, y + 6), "TÉLÉCHARGEMENTS", font=font(9, True), fill=STEAM_BLUE, anchor="lm")
    if not sl.running:
        d.text((W - 10, y + 6), "Steam fermé", font=font(9), fill=MUTED, anchor="rm")
    y += 14
    downloads = sl.downloads[:2]
    if not downloads:
        d.text((12, y + 9), "Aucune mise à jour en cours", font=font(11), fill=MUTED, anchor="lm")
        y += 22
    for dl in downloads:
        panel(d, (6, y, W - 6, y + 34), 5)
        thumb = None
        path = lib.image(dl["appid"], "header") if lib else None
        if path:
            thumb = _thumb(path, 64, 30)
        if thumb:
            img.paste(thumb, (8, y + 2))
        else:
            d.rectangle((8, y + 2, 71, y + 31), fill=TRACK)
        x = 78
        d.text((x, y + 9), fit(d, dl["name"], font(11, True), 150), font=font(11, True),
               fill=TEXT, anchor="lm")
        active = dl["state"] == "téléchargement"
        d.text((W - 12, y + 9), dl["state"], font=font(9, True),
               fill=STEAM_BLUE if active else MUTED, anchor="rm")
        frac = dl["done"] / dl["total"] if dl["total"] else 0
        bar(d, x, y + 19, W - 12 - x - 92, 5, frac, STEAM_BLUE if active else MUTED)
        info = f"{fmt_size(dl['done'])} / {fmt_size(dl['total'])}" if dl["total"] else ""
        if dl["rate"] and active:
            info = f"{dl['rate'] / 2**20:.1f} Mo/s".replace(".", ",") + (f" · {frac * 100:.0f}%"
                                                                          if dl["total"] else "")
        d.text((W - 12, y + 22), info, font=font(9), fill=MUTED, anchor="rm")
        y += 38
    if len(sl.downloads) > 2:
        d.text((W - 10, y - 2), f"+{len(sl.downloads) - 2} autres", font=font(9), fill=MUTED,
               anchor="ra")
        y += 10

    # amis
    y += 4
    friends = sl.friends
    label = f"AMIS EN LIGNE · {len(friends)}" + (f"/{sl.friends_total}" if sl.friends_total else "")
    label = label if not sl.friends_status else "AMIS"
    d.text((10, y + 6), label, font=font(9, True), fill=STEAM_BLUE, anchor="lm")
    d.line((d.textlength(label, font=font(9, True)) + 18, y + 6, W - 10, y + 6), fill=TRACK)
    y += 16
    if sl.friends_status:
        d.text((12, y + 8), fit(d, sl.friends_status, font(10), W - 24), font=font(10),
               fill=MUTED, anchor="lm")
        return
    if not friends:
        d.text((12, y + 8), "Aucun ami en ligne", font=font(11), fill=MUTED, anchor="lm")
        return
    rows = max(1, (H - 4 - y) // 22)
    c.steam_scroll = max(0, min(c.steam_scroll, len(friends) - rows))
    cache = c.discord.avatars if c.discord else None

    def friend_row(li, ld, idx, fy):
        f = friends[idx]
        color = STEAM_GAME if f["game"] else STEAM_BLUE if f["state"] == "en ligne" else MUTED
        avatar(li, ld, cache, f["avatar"], 18, fy + 10, 18, f["name"], ring=color)
        ld.text((34, fy + 10), fit(ld, f["name"], font(11, True), 120), font=font(11, True),
                fill=TEXT, anchor="lm")
        status = f["game"] or f["state"]
        ld.text((W - 10, fy + 10), fit(ld, status, font(10), 150), font=font(10), fill=color,
                anchor="rm")
    smooth_rows(img, "steam_scroll", c.steam_scroll, len(friends), y, min(H - 2, y + rows * 22),
                22, friend_row, t)
    if len(friends) > rows:
        key_hints(d, H - 8, [("▲▼", "")], "right", x=W - 4)


AUDIO_APPS_VISIBLE = 4


def page_audio(d, c, t):
    """Audio du système : sortie et entrée par défaut, volume général, micro, applis."""
    from . import mixer

    vol = c.volume
    if not vol or vol.level is None:
        d.text((W // 2, 120), "Audio indisponible", font=font(16, True), fill=MUTED, anchor="mm")
        if vol and vol.error:
            d.text((W // 2, 144), fit(d, vol.error, font(10), 290), font=font(10), fill=MUTED,
                   anchor="mm")
        return
    c.audio_pick = c.audio_pick or {}
    profs = mixer.profiles(c)
    lines = mixer.rows(vol, profs)
    cur = c.audio_cursor
    sel = lines[cur] if cur is not None and cur < len(lines) else None

    def is_sel(row):
        return sel is not None and row == sel

    moving = []     # surbrillance encore en route : un liseré posé à la fin, par-dessus

    def highlight(y0, y1, row):
        if is_sel(row):
            gy = glide("audio_cursor", y0, t)
            gh = glide("audio_cursor_h", y1 - y0, t)
            if abs(gy - y0) < 0.5:
                panel(d, (4, y0, W - 4, y1), 5, outline=None if _theme == "g19" else ACCENT,
                      color=dim(ACCENT, 0.35) if _theme == "g19" else PANEL)
            else:
                moving.append((gy, gh))

    # profils : une pastille par profil, celui en cours en couleur
    off = 0
    if profs:
        off = 24
        row = {"kind": "profile"}
        highlight(28, 49, row)
        d.text((12, 39), "PROFIL", font=font(9, True), fill=ACCENT, anchor="lm")
        active = vol.active_profile(profs)
        f = font(10, True)
        x, right = 64, W - 12
        if is_sel(row):
            d.text((x, 39), "◄", font=font(10, True), fill=TEXT, anchor="lm")
            d.text((right, 39), "►", font=font(10, True), fill=TEXT, anchor="rm")
            x, right = x + 14, right - 14
        room = (right - x - 4 * (len(profs) - 1)) // len(profs)
        for k, p in enumerate(profs):
            name = fit(d, p["name"], f, room - 10)
            w = min(room, int(d.textlength(name, font=f)) + 14)
            on = k == active
            d.rounded_rectangle((x, 31, x + w, 47), 8, fill=ACCENT if on else TRACK)
            d.text((x + w // 2, 39), name, font=f, fill=BG if on else MUTED, anchor="mm")
            x += w + 4

    # périphériques : sortie puis entrée
    for k, (kind, label) in enumerate((("out", "SORTIE"), ("in", "ENTRÉE"))):
        y = 28 + off + k * 24
        row = {"kind": kind}
        highlight(y, y + 21, row)
        devs, current = mixer.devices(vol, kind)
        i = mixer.picked(c, kind)
        name = devs[i][1] if devs else "aucun périphérique"
        pending = kind in c.audio_pick and devs and devs[i][0] != current
        d.text((12, y + 11), label, font=font(9, True), fill=ACCENT, anchor="lm")
        x = 64
        if is_sel(row) and len(devs) > 1:
            d.text((x, y + 11), "◄", font=font(10, True), fill=TEXT, anchor="lm")
            d.text((W - 12, y + 11), "►", font=font(10, True), fill=TEXT, anchor="rm")
            x += 14
        right = W - 30 if is_sel(row) else W - 12
        count = f"{i + 1}/{len(devs)}" if devs and len(devs) > 1 and not is_sel(row) else ""
        if count:       # le nom s'arrête avant le compteur « 3/10 »
            right -= int(d.textlength(count, font=font(9))) + 6
        if pending:
            right -= 64
            d.text((W - 28, y + 11), "OK appliquer", font=font(9, True), fill=WARN, anchor="rm")
        d.text((x, y + 11), fit(d, name, font(11, True), right - x), font=font(11, True),
               fill=WARN if pending else TEXT, anchor="lm")
        if count:
            d.text((W - 12, y + 11), count, font=font(9), fill=MUTED, anchor="rm")

    # volume général et micro
    def volume_line(y, row, icon, label, level, peak, muted, color):
        highlight(y, y + 21, row)
        icon(d, 12, y + 11, muted, HOT if muted else TEXT)
        d.text((34, y + 11), label, font=font(11, True), fill=TEXT, anchor="lm")
        level_bar(d, 100, y + 8, 160, level or 0, peak, muted, color)
        d.text((W - 12, y + 11), "muet" if muted else f"{(level or 0) * 100:.0f}%",
               font=font(11, True), fill=HOT if muted else TEXT, anchor="rm")

    volume_line(78 + off, {"kind": "master"}, speaker_icon, "Général", vol.level, vol.peak,
                vol.muted, ACCENT)
    y = 102 + off
    if vol.mic_level is not None:
        volume_line(y, {"kind": "mic"}, mic_icon, "Micro", vol.mic_level, vol.mic_peak,
                    vol.mic_muted, OK)
        y += 24

    # applis, avec défilement qui suit le curseur
    d.text((12, y + 8), "APPLIS", font=font(9, True), fill=ACCENT, anchor="lm")
    d.line((54, y + 8, W - 12, y + 8), fill=TRACK)
    apps = vol.sessions
    first_app = len(lines) - len(apps)
    visible = AUDIO_APPS_VISIBLE - (1 if profs else 0)
    top = 0
    if sel and sel["kind"] == "app":
        top = max(0, min(cur - first_app - visible + 1, len(apps) - visible))
        top = min(top, cur - first_app)
    y += 16
    for s in apps[top:top + visible]:
        row = {"kind": "app", "key": s["key"]}
        highlight(y, y + 19, row)
        speaker_icon(d, 12, y + 10, s["muted"], dim(TEXT, 0.8) if not s["muted"] else HOT)
        d.text((34, y + 10), fit(d, s["name"], font(11), 62), font=font(11), fill=TEXT, anchor="lm")
        level_bar(d, 100, y + 7, 160, s["volume"], s["peak"], s["muted"], GPU_C, h=5)
        d.text((W - 12, y + 10), "muet" if s["muted"] else f"{s['volume'] * 100:.0f}%",
               font=font(10), fill=HOT if s["muted"] else MUTED, anchor="rm")
        y += 21
    span = ""
    if len(apps) > visible:
        span = f"{top + 1}-{top + min(visible, len(apps))}/{len(apps)}"
        d.text((W - 12, 236), span,
               font=font(9), fill=MUTED, anchor="rb")

    if cur is not None and sel and sel["kind"] == "profile":
        hints = [("◄►", "profil"), ("▲▼", "ligne"), ("Annuler", "")]
    elif cur is not None:
        hints = [("▲▼", "ligne"), ("◄►", "régler"), ("OK", "muet"), ("Annuler", "")]
    else:
        hints = [("OK", "profils / réglages" if profs else "régler"), ("▲▼", "volume")]
    key_hints(d, 229, hints)
    for gy, gh in moving:
        d.rounded_rectangle((4, gy, W - 4, gy + gh), 5, outline=ACCENT, width=1)


def _luminance(r, g, b):
    """Luminance relative sRGB (0..1), celle des calculs de contraste WCAG."""
    lin = [c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4 for c in (r, g, b)]
    return 0.2126 * lin[0] + 0.7152 * lin[1] + 0.0722 * lin[2]


def media_accent(m):
    """Couleur d'accent du média : celle de la pochette, gardée lisible sur le fond du thème.

    Teinte conservée, saturation ramenée dans une plage franche mais pas fluo, et clarté
    déplacée juste ce qu'il faut pour atteindre le contraste voulu (≈ 7:1 en sombre,
    ≈ 4,5:1 en clair)."""
    import colorsys

    if not m or not m.accent:
        return CLAUDE
    h, l, s = colorsys.rgb_to_hls(*m.accent)
    s = min(max(s, 0.5), 0.85)
    light = _light()
    lo, hi = (0.04, 0.18) if light else (0.32, 0.80)
    if not light:
        l = min(l, 0.82)        # pas de quasi-blanc : la couleur doit rester une couleur

    def lum(x):
        return _luminance(*colorsys.hls_to_rgb(h, x, s))

    if not lo <= lum(l) <= hi:
        # dichotomie sur la clarté vers la borne dépassée
        target = hi if lum(l) > hi else lo
        a, b = (0.0, l) if lum(l) > hi else (l, 1.0)
        for _ in range(20):
            mid = (a + b) / 2
            if lum(mid) < target:
                a = mid
            else:
                b = mid
        l = (a + b) / 2
    r, g, b = colorsys.hls_to_rgb(h, l, s)
    return int(r * 255), int(g * 255), int(b * 255)


def volume_row(d, vol, x, y, w, peak_color=None):
    """Icône + barre de volume (avec vumètre en direct) + pourcentage."""
    if not vol or vol.level is None:
        return
    speaker_icon(d, x, y, vol.muted, MUTED if vol.muted else TEXT)
    bx, bw = x + 22, w - 22 - 36
    d.rounded_rectangle((bx, y - 2, bx + bw, y + 3), 2, fill=TRACK)
    if not vol.muted:
        lw = bw * vol.level
        if lw >= 5:
            d.rounded_rectangle((bx, y - 2, bx + lw, y + 3), 2, fill=dim(TEXT, 0.45))
        pw = lw * min(vol.peak * 1.4, 1.0)
        if pw >= 5:
            d.rounded_rectangle((bx, y - 2, bx + pw, y + 3), 2, fill=peak_color or OK)
    label = "muet" if vol.muted else f"{vol.level * 100:.0f}%"
    d.text((x + w, y), label, font=font(11, True), fill=HOT if vol.muted else TEXT, anchor="rm")


def has_lyrics(c):
    """Le morceau en cours a-t-il des paroles (synchronisées ou non) ? Lance la recherche."""
    data = c.lyrics.get(c.media) if c.lyrics and c.media else None
    return isinstance(data, dict) and bool(data["synced"] or any(l.strip() for l in data["plain"]))


_cover_cache = {}


def _cover_2010(art, size):
    """Pochette vernie (reflet diagonal sur le haut) et son reflet en miroir qui s'estompe."""
    key = (id(art), size)
    hit = _cover_cache.get(key)
    if hit and hit[0] is art:
        return hit[1], hit[2]
    if len(_cover_cache) > 8:
        _cover_cache.clear()
    cov = art.resize((size, size), Image.LANCZOS).convert("RGBA")
    alpha = cov.getchannel("A")
    shine = Image.new("L", (size, size), 0)
    ImageDraw.Draw(shine).polygon([(0, 0), (size, 0), (size, size * 0.32), (0, size * 0.5)],
                                  fill=46)
    gloss = Image.new("RGBA", (size, size), (255, 255, 255, 0))
    gloss.putalpha(ImageChops.multiply(shine, alpha))
    cov = Image.alpha_composite(cov, gloss)
    rh = size * 2 // 5
    refl = cov.transpose(Image.FLIP_TOP_BOTTOM).crop((0, 0, size, rh))
    fade = Image.linear_gradient("L").resize((size, rh)).point(lambda v: max(0, 90 - v * 90 // 255))
    refl.putalpha(ImageChops.multiply(refl.getchannel("A"), fade))
    _cover_cache[key] = (art, cov, refl)
    return cov, refl


def chrome_button(d, cx, cy, r, accent=None):
    """Bouton rond chromé (ou teinté de l'accent) avec reflet sur la moitié haute."""
    img = getattr(d, "_image", None)
    top, bottom = ((200, 206, 216), (40, 44, 52)) if not accent else         (mix(accent, (255, 255, 255), 0.5), mix(accent, (0, 0, 0), 0.55))
    if img is not None:
        g = _vgrad(2 * r + 1, 2 * r + 1, top, bottom)
        m = Image.new("L", g.size, 0)
        ImageDraw.Draw(m).ellipse((0, 0, 2 * r, 2 * r), fill=255)
        img.paste(g, (cx - r, cy - r), m)
    d.ellipse((cx - r, cy - r, cx + r, cy + r), outline=(0, 0, 0))
    d.chord((cx - r + 2, cy - r + 1, cx + r - 2, cy + 2), 180, 360,
            fill=mix(top, (255, 255, 255), 0.35))


_media_bg_cache = {}
_vignette_cache = []
BG_PAN = (420, 315)      # fond un peu plus grand que l'écran, parcouru lentement


def _vignette():
    """Masque d'assombrissement : bords et bas de l'écran (pour la barre de lecture)."""
    if not _vignette_cache:
        small = Image.new("L", (64, 48))
        for y in range(48):
            for x in range(64):
                r = math.hypot((x - 32) / 32, (y - 20) / 30)
                v = min(1.0, max(0.0, (r - 0.55) / 0.75)) * 170
                v += max(0.0, (y - 34) / 14) * 120           # bas plus sombre
                small.putpixel((x, y), int(min(v, 215)))
        _vignette_cache.append(small.resize((W, H), Image.BICUBIC))
    return _vignette_cache[0]


def media_backdrop(m, accent, t):
    """Fond du lecteur G19 : la pochette très floutée, couleurs ravivées et luminosité ramenée
    à un niveau constant (une pochette sombre est éclaircie, une claire assombrie), teintée de
    sa couleur ; elle dérive lentement (effet « Ken Burns ») sous un vignettage."""
    key = (id(m.bg), accent)
    hit = _media_bg_cache.get(key)
    if not hit or hit[0] is not m.bg:
        if len(_media_bg_cache) > 6:
            _media_bg_cache.clear()
        tint = _vgrad(*BG_PAN, mix(accent, (0, 0, 0), 0.35), mix(accent, (0, 0, 0), 0.75))
        if m.bg:
            big = m.bg.resize(BG_PAN, Image.BICUBIC).filter(ImageFilter.GaussianBlur(14))
            big = ImageEnhance.Color(big).enhance(1.5)
            mean = ImageStat.Stat(big.convert("L")).mean[0] / 255
            big = ImageEnhance.Brightness(big).enhance(min(3.5, max(0.5, 0.30 / max(mean, 0.02))))
            big = Image.blend(big, tint, 0.35)
        else:
            big = tint
        hit = _media_bg_cache[key] = (m.bg, big)
    big = hit[1]
    ox = int((BG_PAN[0] - W) * (0.5 + 0.5 * math.sin(t * 0.09)))
    oy = int((BG_PAN[1] - H) * (0.5 + 0.5 * math.cos(t * 0.07)))
    img = big.crop((ox, oy, ox + W, oy + H))
    img.paste((0, 0, 0), (0, 0), _vignette())
    return img


def shadow_text(d, xy, text, fnt, fill, anchor="la"):
    """Texte avec une ombre portée d'un pixel, lisible sur n'importe quel fond."""
    x, y = xy
    d.text((x + 1, y + 1), text, font=fnt, fill=(0, 0, 0), anchor=anchor)
    d.text((x, y), text, font=fnt, fill=fill, anchor=anchor)


ART_FADE = 0.45        # s de fondu d'une pochette à la suivante
_art_state = {}


def animated_art(slot, art, track, t):
    """Pochette à poser : fondu depuis la précédente au changement de morceau (`track`).
    Renvoie (image, décalage x, décalage y)."""
    st = _art_state.setdefault(slot, {"track": None, "img": None, "prev": None, "since": 0.0})
    if track != st["track"]:
        st["prev"] = st["img"] if st["track"] is not None else None
        st["track"], st["since"] = track, t
    st["img"] = art
    out = art
    k = (t - st["since"]) / ART_FADE
    if ANIMATE and st["prev"] is not None and 0 <= k < 1:
        prev = st["prev"] if st["prev"].size == art.size else st["prev"].resize(art.size)
        out = Image.blend(prev.convert("RGBA"), art.convert("RGBA"), 1 - (1 - k) ** 3)
    return out, 0, 0


_eq_levels = {}


_icon_fonts = {}


def icon(d, glyph, cx, cy, size, color):
    """Icône de la police d'icônes de Windows (Segoe Fluent Icons, sinon MDL2)."""
    f = _icon_fonts.get(size)
    if f is None:
        for name in ("SegoeIcons.ttf", "segmdl2.ttf"):
            try:
                f = ImageFont.truetype(name, size)
                break
            except OSError:
                continue
        _icon_fonts[size] = f
    if f is None:
        return False
    d.text((cx, cy), glyph, font=f, fill=color, anchor="mm")
    return True


# icônes des états vides (Segoe Fluent Icons)
ICON_BELL, ICON_LOCK, ICON_MESSAGE, ICON_HISTORY = "\uE7ED", "\uE72E", "\uE8BD", "\uE81C"
ICON_SCREEN, ICON_BOX, ICON_PEOPLE, ICON_BATTERY = "\uE7F4", "\uE7B8", "\uE716", "\uE83F"
ICON_CAR, ICON_GAME, ICON_MOON = "\uE804", "\uE7FC", "\uE708"


def empty_state(d, glyph, title, subtitle="", color=None, cy=118):
    """Page sans contenu : une icône dans un rond, un titre et une phrase qui dit quoi faire."""
    color = color or ACCENT
    d.ellipse((W // 2 - 26, cy - 46, W // 2 + 26, cy + 6), fill=dim(color, 0.18),
              outline=dim(color, 0.5))
    icon(d, glyph, W // 2, cy - 20, 26, color)
    d.text((W // 2, cy + 24), fit(d, title, font(13, True), W - 30), font=font(13, True),
           fill=TEXT, anchor="mm")
    if subtitle:
        d.text((W // 2, cy + 43), fit(d, subtitle, font(10), W - 30), font=font(10),
               fill=MUTED, anchor="mm")


def key_hints(d, y, items, align="left", x=None, color=None):
    """Indications de touches, partout pareilles : chaque touche dans une petite pastille
    (comme une touche du G19), suivie de son action. items : [(touche, action)].
    y : milieu vertical ; align : left / right / center. Renvoie la largeur prise."""
    fk, fl = font(8, True), font(9)
    color = color or ACCENT
    parts = []
    for key, label in items:
        kw = d.textlength(key, font=fk) + 8
        lw = d.textlength(label, font=fl) if label else 0
        parts.append((key, label, kw, lw))
    total = sum(kw + (lw + 4 if lw else 0) for _, _, kw, lw in parts) + 9 * (len(parts) - 1)
    if align == "right":
        x0 = (x if x is not None else W - 10) - total
    elif align == "center":
        x0 = (x if x is not None else W // 2) - total / 2
    else:
        x0 = x if x is not None else 10
    cx = x0
    for key, label, kw, lw in parts:
        d.rounded_rectangle((cx, y - 6, cx + kw, y + 6), 4, outline=dim(color, 0.85), width=1)
        d.text((cx + kw / 2, y), key, font=fk, fill=TEXT, anchor="mm")
        cx += kw
        if lw:
            d.text((cx + 4, y), label, font=fl, fill=dim(MUTED, 0.95), anchor="lm")
            cx += lw + 4
        cx += 9
    return total


def smooth_rows(img, key, scroll, count, top, bottom, row_h, draw_row, t):
    """Liste qui défile en douceur : la position glisse vers la ligne `scroll`, les lignes
    sont dessinées sur un morceau du fond (top → bottom) puis reposées, coupées net aux bords.
    draw_row(image, draw, index, y) dessine la ligne `index` à la hauteur locale `y`."""
    offset = glide(key, scroll * row_h, t, 0.08)
    first = int(offset // row_h)
    frac = offset - first * row_h
    layer = img.crop((0, top, W, bottom))
    ld = ImageDraw.Draw(layer)
    visible = (bottom - top) // row_h + 2
    for idx in range(max(0, first), min(count, first + visible)):
        draw_row(layer, ld, idx, (idx - first) * row_h - frac)
    img.paste(layer, (0, top))
_appear = {}


def appear(key, on, t, duration=0.4, start=False):
    """Opacité 0..1 d'un élément qui apparaît (ou disparaît) en fondu quand `on` change :
    « OK paroles » une fois les paroles trouvées… Une clé nouvelle (autre morceau) part de
    l'état `start` : masqué par défaut, l'élément y apparaît donc toujours en fondu."""
    if key not in _appear:
        if len(_appear) > 64:
            _appear.clear()
        _appear[key] = (start, -1e9)       # état de départ stable, pas « en train de changer »
    state, since = _appear[key]
    if on != state:
        _appear[key] = (on, t)
        state, since = on, t
    k = 1.0 if not ANIMATE else min(1.0, max(0.0, (t - since) / duration))
    k = 1 - (1 - k) ** 2
    return k if on else 1 - k


def faded(img, alpha, draw):
    """Dessine avec `draw(d)` à l'opacité `alpha` (calque transparent quand alpha < 1)."""
    if alpha <= 0.01:
        return
    if alpha >= 0.99:
        draw(ImageDraw.Draw(img))
        return
    layer = Image.new("RGBA", img.size, (0, 0, 0, 0))
    draw(ImageDraw.Draw(layer))
    a = layer.getchannel("A").point(lambda v: int(v * alpha))
    layer.putalpha(a)
    img.paste(layer, (0, 0), layer)


def equalizer(d, key, x, cy, w, h, n, vol, playing, t, color, mirror=False, clip_w=None):
    """Petit égaliseur animé : `n` barres qui montent et descendent autour de la ligne `cy`,
    menées par le niveau réel de la sortie audio (montée vive, retombée douce) ; chaque barre
    a son propre rythme pour que l'ensemble danse. Barres au repos quand la lecture est en
    pause ou les animations coupées."""
    peak = min(1.0, (vol.peak if vol else 0.0) * 1.5) if playing and ANIMATE else 0.0
    levels, last = _eq_levels.get(key, ([0.0] * n, t))
    if len(levels) != n:
        levels = [0.0] * n
    dt = max(0.0, min(0.2, t - last))
    bw = (w - (n - 1) * 3) / n
    for i in range(n):
        k = i if not mirror else n - 1 - i
        wave = 0.5 + 0.5 * math.sin(t * (6.3 + 1.9 * k) + k * 2.4)
        wave2 = 0.5 + 0.5 * math.sin(t * (3.1 + 0.7 * k) + k * 1.3)
        target = peak * (0.25 + 0.75 * (0.6 * wave + 0.4 * wave2))
        tau = 0.04 if target > levels[i] else 0.22
        levels[i] += (target - levels[i]) * (1 - math.exp(-dt / tau)) if dt else 0.0
        bh = max(2.0, levels[i] * h)
        bx = x + i * (bw + 3)
        if clip_w is not None and bx + bw > x + clip_w:
            continue                     # repliée : barres de droite masquées
        d.rounded_rectangle((bx, cy - bh / 2, bx + bw, cy + bh / 2), min(2, bw / 2),
                            fill=color if levels[i] > 0.02 else dim(color, 0.35))
    _eq_levels[key] = (levels, t)


def page_media_2010(img, d, m, t, vol=None, lyrics_hint=False):
    """Lecteur du thème G19 : grande pochette vernie avec son reflet à gauche ; à droite le
    titre, les commandes et le volume ; la barre de lecture sur toute la largeur en bas."""
    accent = media_accent(m) if m.accent else ACCENT   # pochette sans couleur : bleu G19
    bright = mix(accent, (255, 255, 255), 0.2)
    img.paste(media_backdrop(m, accent, t), (0, 0))

    size, cx0, cy0 = 118, 12, 32
    if m.art:
        cov, refl = _cover_2010(m.art, size)
        cov, dx, dy = animated_art("2010", cov, (m.title, m.artist), t)
        img.paste(cov, (cx0 + dx, cy0 + dy), cov)
        img.paste(refl, (cx0, cy0 + size + 2), refl)
    else:
        panel(d, (cx0, cy0, cx0 + size, cy0 + size), 8)
        d.text((cx0 + size // 2, cy0 + size // 2), "♪", font=font(40, True), fill=MUTED,
               anchor="mm")

    # colonne de droite
    x = cx0 + size + 12
    x1 = W - 12
    maxw = x1 - x
    colc = (x + x1) // 2
    app = fit(d, (m.app or "").upper(), font(9, True), maxw - 60)
    app_vol = vol.app_volume(m.app) if vol else None
    if app_vol is not None and app_vol < 0.99:
        app += f" · {app_vol * 100:.0f}%"
    pw = int(d.textlength(app, font=font(9, True))) + 14
    panel(d, (x, 33, x + pw, 47), 6, color=dim(accent, 0.6) if m.playing else TRACK)
    d.text((x + pw / 2, 40), app, font=font(9, True), fill=(255, 255, 255), anchor="mm")
    y = 52
    for line in wrap(d, m.title, font(16, True), maxw, 2):
        shadow_text(d, (x, y), line, font(16, True), (255, 255, 255))
        y += 20
    if m.artist:
        shadow_text(d, (x, y + 2), fit(d, m.artist, font(12, True), maxw), font(12, True),
                    (226, 232, 240))
        y += 17
    if m.album and y + 14 <= 116:
        shadow_text(d, (x, y + 2), fit(d, m.album, font(10), maxw), font(10), (186, 194, 206))

    # commandes : ▲ précédent · lecture/pause · ▼ suivant
    cy = 138
    for dx, r in ((-38, 12), (38, 12)):
        chrome_button(d, colc + dx, cy, r)
    chrome_button(d, colc, cy, 17, accent=accent)
    skip_icon(d, colc - 38, cy, False, (20, 22, 26))
    skip_icon(d, colc + 38, cy, True, (20, 22, 26))
    play_icon(d, colc + (0 if m.playing else 1), cy, m.playing, (255, 255, 255))
    for dx, key in ((-38, "▲"), (38, "▼")):
        d.text((colc + dx, cy + 15), key, font=font(7), fill=(170, 178, 190), anchor="mt")

    # volume
    if vol and vol.level is not None:
        vy = 172
        speaker_icon(d, x, vy, vol.muted, HOT if vol.muted else (226, 232, 240))
        led_bar(d, x + 22, vy - 3, maxw - 56, 5, 0 if vol.muted else vol.level, bright)
        shadow_text(d, (x1, vy), "muet" if vol.muted else f"{vol.level * 100:.0f}%",
                    font(10, True), HOT if vol.muted else (255, 255, 255), anchor="rm")

    # barre de lecture pleine largeur
    x0, xe, by = 12, W - 12, 204
    pos = m.position_at(t)
    d.rounded_rectangle((x0, by, xe, by + 6), 3, fill=(4, 6, 9), outline=(80, 86, 96))
    if m.duration > 0:
        fx = x0 + int((xe - x0) * min(pos / m.duration, 1))
        if fx - x0 >= 6:
            panel(d, (x0, by, fx, by + 6), 3, color=bright if m.playing else MUTED)
        chrome_button(d, fx, by + 3, 5)
        right = f"-{fmt_time(m.duration - pos)}"
    else:
        if m.playing:
            sx = x0 + (t * 60) % (xe - x0 + 40) - 40
            l, r = max(x0, sx), min(xe, sx + 40)
            if r - l >= 6:
                panel(d, (l, by, r, by + 6), 3, color=bright)
        right = "en cours" if m.playing else "en pause"
    shadow_text(d, (x0, by + 12), fmt_time(pos), font(10, True), (255, 255, 255))
    shadow_text(d, (xe, by + 12), right, font(10), (210, 216, 226), anchor="ra")
    faded(img, appear(("hint_2010", m.title, m.artist), bool(lyrics_hint), t),
          lambda dd: shadow_text(dd, (W // 2, by + 12), "OK · paroles", font(9, True), bright,
                                 anchor="ma"))


def page_media(img, d, m, t, vol=None, lyrics_hint=False):
    if _theme == "g19" and m and (m.title or m.artist):
        return page_media_2010(img, d, m, t, vol, lyrics_hint)
    if not m or not (m.title or m.artist):
        d.text((W // 2, 104), "Aucun média", font=font(16, True), fill=MUTED, anchor="mm")
        d.text((W // 2, 128), "Spotify, navigateur, lecteur… s'afficheront ici",
               font=font(11), fill=dim(MUTED, 0.7), anchor="mm")
        if vol:
            volume_row(d, vol, 60, 186, 200)
            d.text((W // 2, 206), fit(d, vol.device, font(10), 280), font=font(10), fill=MUTED,
                   anchor="mm")
        return
    if m.bg:
        img.paste(backdrop(m.bg), (0, 0))
    if m.art:
        art, dx, dy = animated_art("media", m.art, (m.title, m.artist), t)
        img.paste(art, (12 + dx, 34 + dy), art)
    else:
        panel(d, (12, 34, 124, 146), 10)
        d.text((68, 90), "♪", font=font(40, True), fill=MUTED, anchor="mm")

    x, maxw = 136, W - 136 - 10
    app = m.app.upper()
    app_vol = vol.app_volume(m.app) if vol else None
    if app_vol is not None and app_vol < 0.99:
        app += f" · {app_vol * 100:.0f}%"
    accent = media_accent(m)
    d.text((x, 34), app, font=font(10, True), fill=accent if m.playing else MUTED)
    y = 50
    for line in wrap(d, m.title, font(15, True), maxw, 2):
        d.text((x, y), line, font=font(15, True), fill=TEXT)
        y += 20
    if m.artist:
        d.text((x, y + 2), fit(d, m.artist, font(12), maxw), font=font(12), fill=TEXT)
        y += 18
    if m.album:
        d.text((x, y + 2), fit(d, m.album, font(11), maxw), font=font(11), fill=MUTED)
    volume_row(d, vol, x, 140, maxw, accent)

    # progression
    if m.duration > 0:
        pos = m.position_at(t)
        bar(d, 12, 160, 296, 5, pos / m.duration, accent if m.playing else MUTED)
        d.text((12, 172), fmt_time(pos), font=font(11), fill=TEXT)
        d.text((308, 172), fmt_time(m.duration), font=font(11), fill=MUTED, anchor="ra")
        if m.playing:
            d.text((W // 2, 172), f"-{fmt_time(m.duration - pos)}", font=font(11), fill=MUTED,
                   anchor="ma")
    else:
        # durée pas encore publiée par l'appli (vidéo dans un navigateur…) : barre animée et
        # temps écoulé compté depuis le début du média
        pos = m.position_at(t)
        bar(d, 12, 160, 296, 5, 0, MUTED)
        if m.playing:
            x0 = 12 + (t * 70) % 336 - 40
            l, r = max(12, x0), min(308, x0 + 40)
            if r - l >= 5:
                d.rounded_rectangle((l, 160, r, 165), 2, fill=dim(accent, 0.8))
        d.text((12, 172), fmt_time(pos), font=font(11), fill=TEXT)
        d.text((308, 172), "en cours de lecture" if m.playing else "en pause",
               font=font(11), fill=MUTED, anchor="ra")

    # contrôles (▲ précédent · OK lecture/pause · ▼ suivant), encadrés par l'égaliseur
    cy = 212
    eq_color = accent if m.playing else MUTED
    equalizer(d, "media_l", 14, cy, 72, 26, 8, vol, m.playing, t, eq_color, mirror=True)
    hint = appear(("hint_media", m.title, m.artist), bool(lyrics_hint), t)
    # à droite : l'égaliseur se replie en douceur pour laisser la place à « OK paroles »
    equalizer(d, "media_r", 234, cy, 72, 26, 8, vol, m.playing, t, eq_color,
              clip_w=72 - 36 * hint)
    skip_icon(d, 110, cy, False, TEXT)
    d.ellipse((W // 2 - 16, cy - 16, W // 2 + 16, cy + 16), fill=TEXT)
    play_icon(d, W // 2 + (0 if m.playing else 1), cy, m.playing, BG)
    skip_icon(d, 210, cy, True, TEXT)
    for cx, key in ((110, "▲"), (210, "▼")):
        d.text((cx, cy + 14), key, font=font(9), fill=MUTED, anchor="mt")
    def hint_text(dd):
        dd.text((W - 10, cy - 6), "OK", font=font(9, True), fill=accent, anchor="rm")
        dd.text((W - 10, cy + 6), "paroles", font=font(9, True), fill=accent, anchor="rm")
    faded(img, hint, hint_text)


# --- Jeux --------------------------------------------------------------------------------------

def fmt_duration(sec):
    sec = int(sec)
    if sec < 3600:
        return f"{sec // 60} min"
    return f"{sec // 3600} h {sec // 60 % 60:02d}"


def fmt_hours(sec):
    return f"{sec / 3600:.0f} h" if sec >= 3600 else f"{sec // 60:.0f} min"


def fmt_ago(sec):
    if sec < 120:
        return "à l'instant"
    if sec < 3600:
        return f"il y a {int(sec // 60)} min"
    if sec < 86400:
        return f"il y a {int(sec // 3600)} h"
    days = int(sec // 86400)
    return "hier" if days == 1 else f"il y a {days} j"


def placeholder_cover(d, box, name):
    panel(d, box, 6)
    initials = "".join(w[0] for w in re.findall(r"\w+", name)[:2]).upper() or "?"
    cx, cy = (box[0] + box[2]) / 2, (box[1] + box[3]) / 2
    size = 26 if box[2] - box[0] > 50 else 12
    d.text((cx, cy), initials, font=font(size, True), fill=MUTED, anchor="mm")


def chip(d, x, y, w, label, value, color=None):
    color = color or TEXT
    panel(d, (x, y, x + w, y + 30), 5)
    d.text((x + w / 2, y + 10), value, font=font(13, True), fill=color, anchor="mm")
    d.text((x + w / 2, y + 23), label, font=font(9), fill=MUTED, anchor="mm")


def downsample(values, n):
    vals = list(values)
    if len(vals) <= n:
        return vals
    step = len(vals) / n
    out = []
    for i in range(n):
        chunk = vals[int(i * step):int((i + 1) * step)] or [vals[int(i * step)]]
        out.append(sum(chunk) / len(chunk))
    return out


def page_games(img, d, games, t):
    s = games.session if games else None
    if s:
        bg = games.image(s, "bg")
        if bg:
            img.paste(backdrop(bg), (0, 0))
        cover = games.image(s, "cover")
        if cover:
            img.paste(cover, (8, 30), cover)
        else:
            placeholder_cover(d, (8, 30, 92, 156), s.name)

        x, maxw = 102, W - 102 - 8
        y = 28
        for line in wrap(d, s.name, font(15, True), maxw, 2):
            d.text((x, y), line, font=font(15, True), fill=TEXT)
            y += 19
        label = "EN JEU DEPUIS" + (f" · {s.launcher.upper()}" if s.launcher else "")
        d.text((x, 70), label, font=font(9, True), fill=CLAUDE)
        d.text((x, 80), fmt_time(s.duration), font=font(22, True), fill=TEXT)
        total, _src = games.total_seconds(s)
        line = f"aujourd'hui {fmt_duration(games.today_seconds(t))} · total {fmt_hours(total)}"
        d.text((x, 110), fit(d, line, font(11), maxw), font=font(11), fill=MUTED)

        st = s.stats()
        cw = (maxw - 8) / 3
        chip(d, x, 128, cw, "FPS moy.", f"{st['avg']:.0f}" if st else "—")
        chip(d, x + cw + 4, 128, cw, "1% low", f"{st['low1']:.0f}" if st else "—")
        chip(d, x + 2 * (cw + 4), 128, cw, "GPU max", f"{s.temp_max:.0f}°" if s.temp_max else "—",
             temp_color(s.temp_max) if s.temp_max else TEXT)

        panel(d, (6, 164, W - 6, 236), 6)
        d.text((14, 168), "FPS sur la session", font=font(10, True), fill=MUTED)
        if s.power_n:
            d.text((W - 14, 168), f"{s.power_sum / s.power_n:.0f} W moy.", font=font(10),
                   fill=MUTED, anchor="ra")
        pts = downsample(s.fps, 150)
        if len(pts) >= 2:
            sparkline(d, 14, 184, W - 28, 46, pts, ACCENT, vmax=max(pts) * 1.15, panel=None)
        return

    d.text((10, 30), "Derniers jeux", font=font(13, True), fill=TEXT)
    recent = games.recent(4) if games else []
    if not recent:
        d.text((W // 2, 120), "Aucune session enregistrée", font=font(14, True), fill=MUTED,
               anchor="mm")
        d.text((W // 2, 142), "lance un jeu : RTSS le détecte avec ses FPS", font=font(11),
               fill=dim(MUTED, 0.7), anchor="mm")
        return
    d.text((W - 10, 32), f"aujourd'hui {fmt_duration(games.today_seconds(t))}", font=font(11),
           fill=MUTED, anchor="ra")
    for i, r in enumerate(recent):
        y = 50 + i * 47
        panel(d, (6, y, W - 6, y + 43), 6)
        thumb = games.image(r, "thumb")
        if thumb:
            img.paste(thumb, (10, y - 1), thumb)
        else:
            placeholder_cover(d, (10, y + 2, 34, y + 41), r["name"])
        d.text((48, y + 12), fit(d, r["name"], font(13, True), 190), font=font(13, True),
               fill=TEXT, anchor="lm")
        ago = t - (r["start"] + r["duration"])
        detail = f"{fmt_ago(ago)} · {fmt_duration(r['duration'])}"
        if r.get("fps_avg"):
            detail += f" · {r['fps_avg']:.0f} fps"
        d.text((48, y + 30), fit(d, detail, font(11), 206), font=font(11), fill=MUTED, anchor="lm")
        total, _src = games.total_seconds(r)
        if total:
            d.text((W - 14, y + 12), fmt_hours(total), font=font(12, True), fill=TEXT, anchor="rm")
            d.text((W - 14, y + 30), (r.get("launcher") or "total").lower(), font=font(9),
                   fill=MUTED, anchor="rm")


# --- Discord -----------------------------------------------------------------------------------

def avatar(img, d, cache, url, cx, cy, size, name, ring=None, color=None):
    """Avatar rond : `url` est une URL (via `cache`) ou directement une image PIL."""
    color = color or DISCORD
    if ring:
        d.ellipse((cx - size / 2 - 3, cy - size / 2 - 3, cx + size / 2 + 3, cy + size / 2 + 3),
                  fill=ring)
        d.ellipse((cx - size / 2 - 1, cy - size / 2 - 1, cx + size / 2 + 1, cy + size / 2 + 1),
                  fill=BG)
    im = url if isinstance(url, Image.Image) else cache.get(url, size) if cache and url else None
    if im:
        if im.size != (size, size):
            im = im.resize((size, size), Image.LANCZOS)
        img.paste(im, (int(cx - size / 2), int(cy - size / 2)), im)
    else:
        d.ellipse((cx - size / 2, cy - size / 2, cx + size / 2, cy + size / 2), fill=color)
        d.text((cx, cy), (name[:1] or "?").upper(), font=font(int(size * 0.45), True), fill=TEXT,
               anchor="mm")


def toast(img, d, n, cache):
    """Bandeau de notification posé par-dessus la page. n : {source, title, body, icon, color}."""
    color = n["color"]
    panel(d, (6, 196, W - 6, 236), 8, color=dim(color, 0.22))
    d.rounded_rectangle((6, 196, 10, 236), 2, fill=color)
    if n["source"] == "Alerte":
        d.ellipse((17, 203, 43, 229), fill=color)
        d.polygon([(30, 207), (21, 224), (39, 224)], fill=TEXT)
        d.text((30, 219), "!", font=font(10, True), fill=color, anchor="mm")
    else:
        avatar(img, d, cache, n["icon"], 30, 216, 26, n["title"] or n["source"], color=color)
    src = fit(d, n["source"], font(9, True), 120)
    sw = d.textlength(src, font=font(9, True))
    d.text((W - 14, 206), src, font=font(9, True), fill=color, anchor="rm")
    d.text((50, 206), fit(d, n["title"], font(12, True), W - 76 - sw), font=font(12, True),
           fill=TEXT, anchor="lm")
    hw = toast_keys(d, n, color) if "open" in n else 0
    d.text((50, 225), fit(d, n["body"], font(11), W - 66 - hw), font=font(11), fill=TEXT,
           anchor="lm")


def toast_keys(d, n, color):
    """Touches du bandeau en bas à droite : [OK] ouvrir (si sa page existe) · [✕] fermer.
    Renvoie la largeur prise, pour raccourcir le texte du message."""
    f, fb = font(8), font(8, True)
    items = ([("OK", "ouvrir")] if n.get("open") else []) + [("Annuler", "")]
    x = W - 14
    for key, label in reversed(items):
        if label:
            x -= d.textlength(label, font=f)
            d.text((x, 226), label, font=f, fill=dim(TEXT, 0.75), anchor="lm")
            x -= 3
        kw = d.textlength(key, font=fb) + 6
        d.rounded_rectangle((x - kw, 220, x, 232), 3, outline=dim(color, 0.9), width=1)
        d.text((x - kw / 2, 226), key, font=fb, fill=TEXT, anchor="mm")
        x -= kw + 6
    return W - 14 - x + 4


TOAST_IN, TOAST_OUT = 0.35, 0.3   # durée de l'entrée / de la sortie en glissant (s)


def slide_toast(img, n, cache, t, seconds):
    """Bandeau qui monte du bas de l'écran, puis redescend à la fin de sa durée."""
    age = t - n.get("at", t)
    k = 1.0
    if age < TOAST_IN:
        k = 1 - (1 - age / TOAST_IN) ** 3                  # arrivée amortie
    elif age > seconds - TOAST_OUT:
        k = max(0.0, (seconds - age) / TOAST_OUT) ** 2     # départ qui accélère
    offset = int(round((1 - k) * (H - 196 + 2)))
    if offset >= H - 196:
        return
    layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    toast(layer, ImageDraw.Draw(layer), n, cache)
    img.paste(layer, (0, offset), layer)


def ignored(c, item):
    """Notification Windows à ne pas afficher (appli ignorée, ou Discord déjà suivi en RPC)."""
    app = item["app"].lower()
    if app in (a.lower() for a in c.settings["notif_ignore"]):
        return True
    return app == "discord" and c.discord is not None and c.discord.status == "connecté"


def current_toast(c, page, t):
    """La notification la plus récente encore dans sa durée d'affichage, ou None.
    "open" : OK peut ouvrir sa page (elle est affichée parmi les pages, et pas déjà à l'écran)."""
    cands = [(n["at"], n) for n in toast_candidates(c, page, t)
             if t - n["at"] < c.settings["toast_seconds"] and n["at"] > c.toast_closed]
    if not cands:
        return None
    n = max(cands, key=lambda x: x[0])[1]
    pages = c.pages or c.settings.get("pages") or []
    n["open"] = bool(n.get("url") or n.get("session")) or \
        (bool(n.get("page")) and n["page"] in pages and n["page"] != page)
    return n


def toast_candidates(c, page, t):
    """Tous les bandeaux connus (le dernier de chaque source), avec leur horodatage "at"."""
    cands = []
    dc, wn = c.discord, c.notifs
    ve = dc.voice_event if dc and c.settings.get("voice_toasts", True) else None
    if ve:
        cands.append((ve[3], {"page": "discord", "source": "Vocal", "title": ve[0], "body": ve[1], "icon": ve[2],
                              "color": OK if "rejoint" in ve[1] else MUTED}))
    if dc and dc.notifications and c.settings["discord_toasts"] and page != "discord":
        n = dc.notifications[0]
        # en haut à droite : le groupe ou « #salon · serveur » plutôt que « Discord »
        cands.append((dc.last_notification, {"page": "discord",
                                             "url": dc.channel_url(n.get("channel_id")),
                                             "source": n.get("where") or "Discord",
                                             "title": n["author"],
                                             "body": n["body"], "icon": n["icon"],
                                             "color": DISCORD}))
    dn = c.dnd.event if c.dnd else None
    if dn:
        cands.append((dn[2], {"page": "notifs", "source": "Windows", "title": dn[0],
                              "body": dn[1], "icon": None, "color": ACCENT}))
    quiet_win = bool(c.dnd and c.dnd.active)
    if wn and wn.items and c.settings["win_toasts"] and page != "notifs" and not quiet_win:
        n = wn.items[0]
        if not ignored(c, n):
            cands.append((wn.last_time, {"page": "notifs", "source": n["app"], "title": n["title"],
                                         "body": n["body"], "icon": n["icon"], "color": ACCENT}))
    sf = c.steam.event if c.steam and c.settings.get("steam_toasts", True) else None
    if sf:
        cands.append((sf[3], {"page": "steam", "source": "Steam", "title": sf[0], "body": sf[1], "icon": sf[2],
                              "color": STEAM_BLUE}))
    st = c.streaming.event if c.streaming and c.settings.get("stream_toasts", True) else None
    if st:
        cands.append((st[2], {"source": "Streaming", "title": st[0], "body": st[1], "icon": None,
                              "color": HOT if st[1].startswith("connecté") else MUTED}))
    ce = c.claude_event if c.settings.get("claude_reminders", True) else None
    if ce:
        cands.append((ce[2], {"page": "claude", "session": ce[3], "source": "Claude",
                              "title": ce[0], "body": ce[1], "icon": None, "color": CLAUDE}))
    we = c.weather.event if c.weather and c.settings.get("rain_toasts", True) else None
    if we:
        cands.append((we[2], {"page": "weather", "source": "Météo", "title": we[0],
                              "body": we[1], "icon": None, "color": ACCENT}))
    fe = c.fuel.event if c.fuel and c.settings.get("fuel_toasts", True) else None
    if fe:
        cands.append((fe[2], {"page": "fuel", "source": "Carburant", "title": fe[0], "body": fe[1],
                              "icon": None, "color": HOT if "rupture" in fe[1] else OK}))
    dk = c.docker.event if c.docker and c.settings.get("docker_toasts", True) else None
    if dk:
        cands.append((dk[2], {"page": "docker", "source": "Docker", "title": dk[0], "body": dk[1], "icon": None,
                              "color": HOT}))
    dv = c.driver.event if c.driver and c.settings.get("driver_toasts", True) else None
    if dv:
        cands.append((dv[2], {"page": "gpu", "source": "Pilote", "title": dv[0], "body": dv[1], "icon": None,
                              "color": WARN}))
    ue = c.updater.event if c.updater else None
    if ue:
        cands.append((ue[2], {"source": "Mise à jour", "title": ue[0], "body": ue[1],
                              "icon": None, "color": OK if "mis à jour" in ue[0] else ACCENT}))
    le = c.lgs_event
    if le:
        cands.append((le[2], {"source": "LGS", "title": le[0], "body": le[1], "icon": None,
                              "color": WARN}))
    ae = c.agent_event
    if ae:
        cands.append((ae[2], {"source": "Attention", "title": ae[0], "body": ae[1], "icon": None,
                              "color": WARN}))
    pe = c.pages_event
    if pe:
        cands.append((pe[2], {"page": pe[3] if len(pe) > 3 else None, "source": "Écrans", "title": pe[0], "body": pe[1], "icon": None,
                              "color": ACCENT}))
    sy = c.sysw.event if c.sysw else None
    if sy:
        cands.append((sy[2], {"page": "system", "source": "Système", "title": sy[0], "body": sy[1], "icon": None,
                              "color": WARN}))
    ne = c.net.event if c.net else None
    if ne:
        cands.append((ne[2], {"page": "network", "source": "En jeu", "title": ne[0], "body": ne[1], "icon": None,
                              "color": WARN}))
    se = c.saved_event
    if se:
        cands.append((se[2], {"source": "Utilitaire", "title": se[0], "body": se[1], "icon": None,
                              "color": OK}))
    de = c.devices.event if c.devices and c.settings.get("device_toasts", True) else None
    if de:
        cands.append((de[2], {"source": "Périphérique", "title": de[0], "body": de[1],
                              "icon": None, "color": ACCENT}))
    be = c.batteries.event if c.batteries else None
    if be:
        cands.append((be[2], {"page": "batteries", "source": "Batterie", "title": be[0],
                              "body": be[1], "icon": None,
                              "color": OK if be[1].startswith("connecté") else
                              MUTED if be[1] == "déconnecté" else WARN}))
    fe = c.fans.event if c.fans else None
    if fe:
        cands.append((fe[2], {"page": "system", "source": "Ventilos", "title": fe[0], "body": fe[1], "icon": None,
                              "color": WARN if "sécurité" in fe[1] else ACCENT}))
    m = c.media
    key = (m.title, m.artist) if m and m.title else None
    if key != c.media_key:
        # pas de bandeau pour le morceau trouvé au lancement, ni à l'arrêt de la lecture
        if key and c.media_key is not None:
            c.media_changed = t
        c.media_key = key or ()
    if key and c.settings.get("media_toasts", True) and page != "media" and c.media_changed:
        cands.append((c.media_changed, {"page": "media", "source": m.app or "Média", "title": m.title,
                                        "body": m.artist, "icon": m.art,
                                        "color": media_accent(m)}))
    al = c.alerts
    if al and al.newest in al.active:
        title, body = al.describe(al.newest)
        cands.append((al.last_new, {"page": "system", "source": "Alerte", "title": title, "body": body,
                                    "icon": None, "color": HOT}))
    return [{**n, "at": at} for at, n in cands if at]


def page_notifs(img, d, c, t):
    wn = c.notifs
    if not wn or wn.status != "ok":
        status = wn.status if wn else "indisponible"
        if status == "accès refusé":
            empty_state(d, ICON_LOCK, "Accès aux notifications refusé",
                        "Paramètres → Confidentialité → Notifications", WARN)
        else:
            empty_state(d, ICON_BELL, "Notifications Windows indisponibles", status)
        return
    items = [n for n in list(wn.items) if not ignored(c, n)]
    dnd = c.dnd if c.dnd and c.dnd.supported else None
    quiet = bool(dnd and dnd.active)
    if quiet:      # bandeau d'état : la lune, et ce que ça change
        panel(d, (6, 27, W - 6, 45), 6, color=dim(ACCENT, 0.22))
        icon(d, ICON_MOON, 18, 36, 11, ACCENT)
        d.text((30, 36), "Ne pas déranger", font=font(11, True), fill=TEXT, anchor="lm")
    else:
        d.text((10, 36), "Notifications Windows", font=font(12, True), fill=TEXT, anchor="lm")
    key_hints(d, 36, ([("OK", "réactiver" if quiet else "ne pas déranger")] if dnd else [])
              + [("▼", "effacer")], "right")
    if not items:
        empty_state(d, ICON_BELL, "Aucune notification", "les nouvelles s'afficheront ici",
                    cy=132)
        return
    for i, n in enumerate(items[:5]):
        y = 50 + i * 37
        panel(d, (6, y, W - 6, y + 33), 6)
        avatar(img, d, None, n["icon"], 22, y + 16, 22, n["app"], color=ACCENT)
        d.text((40, y + 9), fit(d, n["app"], font(9, True), 200), font=font(9, True), fill=ACCENT,
               anchor="lm")
        d.text((W - 12, y + 9), fmt_age(t - n["time"]), font=font(9), fill=MUTED, anchor="rm")
        line = n["title"] + (f" — {n['body']}" if n["body"] else "")
        d.text((40, y + 23), fit(d, line, font(11), W - 54), font=font(11), fill=TEXT, anchor="lm")


def page_discord(img, d, dc, t):
    if not dc or dc.status != "connecté":
        status = dc.status if dc else "indisponible"
        empty_state(d, ICON_PEOPLE, "Discord",
                    "à configurer : utilitaire → Services → Discord" if status == "non configuré"
                    else status, DISCORD)
        return

    y = 28
    v = dc.voice
    if v:
        panel(d, (6, 28, W - 6, 124), 6)
        speaker_icon(d, 14, 39, False, OK)
        name = fit(d, v["name"], font(13, True), 150)
        d.text((36, 39), name, font=font(13, True), fill=TEXT, anchor="lm")
        if v.get("guild"):
            gx = 36 + d.textlength(name, font=font(13, True)) + 6
            d.text((gx, 40), fit(d, v["guild"], font(10), 230 - gx), font=font(10), fill=MUTED,
                   anchor="lm")
        state = "SOURDINE" if dc.self_deaf else "MUET" if dc.self_mute else "micro ouvert"
        d.text((W - 14, 39), state, font=font(10, True),
               fill=HOT if dc.self_deaf or dc.self_mute else OK, anchor="rm")
        members = sorted(v["members"].values(), key=lambda m: (not m["me"], m["name"].lower()))
        for i, m in enumerate(members[:10]):
            cx = 36 + (i % 5) * 62
            cy = 66 + (i // 5) * 36
            avatar(img, d, dc.avatars, m["avatar"], cx, cy, 24, m["name"],
                   ring=OK if m["speaking"] else None)
            if m["mute"] or m["deaf"]:
                d.ellipse((cx + 6, cy + 5, cx + 14, cy + 13), fill=HOT)
            d.text((cx, cy + 19), fit(d, m["name"], font(9), 58), font=font(9),
                   fill=TEXT if m["speaking"] else MUTED, anchor="mm")
        if len(members) > 10:
            d.text((W - 12, 118), f"+{len(members) - 10}", font=font(10), fill=MUTED, anchor="rb")
        y = 130
    else:
        d.text((10, 36), "Pas en vocal", font=font(11), fill=MUTED, anchor="lm")
        y = 48

    if not dc.notifications:
        d.text((W // 2, (y + 236) // 2), "Aucun message reçu depuis le lancement",
               font=font(11), fill=MUTED, anchor="mm")
        return
    rows = (238 - y) // 36
    for i, n in enumerate(list(dc.notifications)[:rows]):
        ry = y + i * 36
        # panneau du thème (reflet G19, verre Aero…) comme les autres listes, liseré Discord
        panel(d, (6, ry - 1, W - 6, ry + 33), 6)
        d.rounded_rectangle((6, ry - 1, 9, ry + 33), 2, fill=DISCORD)
        avatar(img, d, dc.avatars, n["icon"], 22, ry + 16, 24, n["author"])
        author = fit(d, n["author"], font(12, True), 150)
        d.text((42, ry + 8), author, font=font(12, True), fill=TEXT, anchor="lm")
        where = n.get("where")
        if where:
            ax = 42 + d.textlength(author, font=font(12, True)) + 6
            d.text((ax, ry + 9), fit(d, where, font(9), 270 - ax), font=font(9),
                   fill=MUTED, anchor="lm")
        d.text((W - 12, ry + 8), fmt_age(t - n["time"]), font=font(9), fill=MUTED, anchor="rm")
        d.text((42, ry + 24), fit(d, n["body"], font(11), W - 56), font=font(11),
               fill=dim(TEXT, 0.85), anchor="lm")


# --- Assemblage --------------------------------------------------------------------------------

DATA_READY = {
    "weather": lambda c: c.weather and c.weather.data,
    "steam": lambda c: c.steam and (c.steam.friends or c.steam.downloads),
    "fuel": lambda c: c.fuel and c.fuel.stations,
}


def render(page, c, t=None, post=True):
    """Image 320×240 de la page `page` (id de settings.PAGE_TITLES) ; `post` False : sans la
    passe finale du thème (miniatures du coverflow, filtrées avec le reste)."""
    apply_theme(c)
    t = t or time.time()
    img = canvas()
    d = ImageDraw.Draw(img)
    pages = c.pages or c.settings["pages"]
    # données qui arrivent d'Internet (météo, Steam, Carburant) : elles apparaissent en fondu
    ready = DATA_READY.get(page)
    base = img.copy() if ready else None
    if page == "media":  # les fonds pleine page sont posés avant le bandeau
        if c.show_lyrics and has_lyrics(c):
            page_lyrics(img, d, c.media, c.lyrics, t, c.settings.get("animations", True))
        else:
            page_media(img, d, c.media, t, c.volume, has_lyrics(c))
    elif page == "games":
        page_games(img, d, c.games, t)
    elif page == "audio":
        page_audio(d, c, t)
    elif page == "steam":
        page_steam(img, d, c, t)
    elif page == "history":
        page_history(d, c, t)
    elif page == "batteries":
        page_batteries(d, c, t)
    elif page == "docker":
        page_docker(d, c, t)
    elif page == "fuel":
        page_fuel(d, c, t)
    elif page == "toasts":
        page_toasts(img, d, c, t)
    elif page == "screen":
        page_screen(img, d, c, t)
    elif page == "network":
        page_network(d, c, t)
    elif page == "system":
        strip = c.sessions if c.claude_open and claude_active(c.sessions, c.settings) else None
        page_system(d, c.stats, c.gpu, strip, t, c.media, c.fans)
    elif page == "gpu":
        page_gpu(d, c.stats, c.gpu, t, c.settings["gpu_power_max"], c.gpu_view)
    elif page == "discord":
        page_discord(img, d, c.discord, t)
    elif page == "notifs":
        page_notifs(img, d, c, t)
    elif page == "speedtest":
        page_speedtest(d, c.speedtest, t)
    elif page == "weather":
        page_weather(d, c.weather, t)
    elif page == "vpn":
        page_vpn(d, c.vpn, t)
    elif page == "claude":
        page_claude(d, c.sessions, t, c.scroll, c.usage, c.claude_sel, c.git)
    else:
        page_cores(d, c.stats, t, c.gpu.s if c.gpu else None)
    if base is not None:
        have = bool(ready(c))
        alpha = appear(("data", page), have, t, 0.5)
        if have and alpha < 0.99:     # pas encore là : le message d'attente reste visible
            img.paste(Image.blend(base, img, max(0.0, alpha)))
    title = PAGE_TITLES.get(page, page)
    if page == "system":
        lt = time.localtime(t)
        title = f"{JOURS[lt.tm_wday].capitalize()} {lt.tm_mday} {MOIS[lt.tm_mon - 1]}"
    elif page == "media" and c.show_lyrics and has_lyrics(c):
        title = "Paroles"
    header(d, pages.index(page) if page in pages else 0, len(pages),
           c.sessions if c.claude_open else None, t, c.discord, c.alerts, title,
           c.settings.get("claude_strip_seconds", 10), c.streaming,
           c.batteries.hyperx if c.batteries and getattr(c.batteries, "hyperx", None)
           and c.settings.get("headset_mic", True) else None)
    if c.alerts and c.alerts.active and (t * 2) % 2 < 1.4:
        d.rectangle((0, 0, W - 1, H - 1), outline=HOT, width=2)  # cadre rouge clignotant

    n = current_toast(c, page, t)
    if n:
        slide_toast(img, n, c.discord.avatars if c.discord else None, t,
                    c.settings["toast_seconds"])
    return postprocess(img) if post else img


# --- Test de débit -----------------------------------------------------------------------------

PHASES = {"ping": "Latence…", "download": "Descendant…", "upload": "Montant…"}


def fmt_mbps(v):
    if v is None:
        return "—"
    return f"{v / 1000:.2f} Gb/s" if v >= 1000 else f"{v:.0f} Mb/s"


def speed_gauge(d, cx, cy, r, value, vmax, color, label):
    box = (cx - r, cy - r, cx + r, cy + r)
    frac = math.sqrt(max(value, 0) / vmax) if vmax else 0  # échelle racine : lisible de 10 à 1000
    if _theme == "g19":   # compteur à segments lumineux
        segs = 32
        for k in range(segs):
            a0 = 150 + k * 240 / segs + 1
            on = (k + 0.5) / segs <= min(frac, 1.0)
            d.arc(box, a0, a0 + 240 / segs - 2.5,
                  fill=mix(color, (255, 255, 255), 0.25 * k / segs) if on
                  else mix((6, 9, 13), color, 0.15), width=10)
        d.arc((cx - r + 14, cy - r + 14, cx + r - 14, cy + r - 14), 150, 390,
              fill=(60, 64, 72), width=1)
    else:
        d.arc(box, 150, 390, fill=TRACK, width=10)
        if frac > 0.005:
            d.arc(box, 150, 150 + 240 * min(frac, 1.0), fill=color, width=10)
    for mark in (10, 100, 500, 1000, 2500):
        if mark <= vmax:
            a = math.radians(150 + 240 * math.sqrt(mark / vmax))
            tx, ty = cx + (r + 12) * math.cos(a), cy + (r + 12) * math.sin(a)
            d.text((tx, ty), str(mark) if mark < 1000 else f"{mark // 1000}G" if mark % 1000 == 0
                   else "2.5G", font=font(8), fill=MUTED, anchor="mm")
    d.text((cx, cy - 4), f"{value:.0f}", font=font(30, True), fill=TEXT, anchor="mm")
    d.text((cx, cy + 20), "Mbit/s", font=font(10), fill=MUTED, anchor="mm")
    d.text((cx, cy + r - 2), label, font=font(11, True), fill=color, anchor="mm")


def result_cols(d, y, ping, jitter, down, up):
    cols = [("PING", f"{ping:.0f} ms" if ping is not None else "—",
             f"gigue {jitter:.0f} ms" if jitter is not None else ""),
            ("DESCENDANT", fmt_mbps(down), ""), ("MONTANT", fmt_mbps(up), "")]
    for i, (label, value, sub) in enumerate(cols):
        cx = 55 + i * 105
        d.text((cx, y), label, font=font(9, True), fill=MUTED, anchor="mm")
        d.text((cx, y + 18), value, font=font(15, True), fill=TEXT, anchor="mm")
        if sub:
            d.text((cx, y + 35), sub, font=font(9), fill=MUTED, anchor="mm")


def page_speedtest(d, sp, t):
    if not sp:
        return
    if sp.running:
        vmax = 2500 if sp.peak > 1000 else 1000
        color = OK if sp.phase == "download" else ACCENT if sp.phase == "upload" else WARN
        value = sp.live if sp.phase in ("download", "upload") else 0
        speed_gauge(d, W // 2, 108, 66, value, vmax, color, PHASES.get(sp.phase, ""))
        bar(d, 40, 184, 240, 4, sp.progress, color)
        result_cols(d, 200, sp.ping, sp.jitter, sp.down, None if sp.phase != "upload" else sp.live)
        key_hints(d, 38, [("OK", "annuler")], "right")
        return

    last = sp.history[0] if sp.history else None
    if not last:
        # pas encore de test : une invitation au centre
        speed_gauge(d, W // 2, 104, 52, 0, 1000, ACCENT, "")
        d.text((W // 2, 178), "Aucun test pour l'instant", font=font(13, True), fill=TEXT,
               anchor="mm")
        d.text((W // 2, 196), "serveurs speed.cloudflare.com", font=font(9),
               fill=dim(MUTED, 0.8), anchor="mm")
        speed_button(d, 220, "lancer un test")
        return

    # dernier résultat : deux grandes cartes
    for k, (label, value, color, arrow) in enumerate(
            (("DESCENDANT", last["down"], OK, "↓"), ("MONTANT", last["up"], ACCENT, "↑"))):
        x0 = 6 + k * 157
        panel(d, (x0, 30, x0 + 151, 88), 8)
        d.rounded_rectangle((x0, 30, x0 + 3, 88), 2, fill=color)
        d.text((x0 + 12, 41), f"{arrow} {label}", font=font(9, True), fill=color, anchor="lm")
        num, unit = speed_parts(value)
        d.text((x0 + 12, 66), num, font=font(26, True), fill=TEXT, anchor="lm")
        d.text((x0 + 16 + d.textlength(num, font=font(26, True)), 72), unit, font=font(10),
               fill=MUTED, anchor="lm")
    ping = f"ping {last['ping']:.0f} ms" + (f" · gigue {last['jitter']:.0f} ms"
                                           if last.get("jitter") is not None else "")
    d.text((10, 100), ping, font=font(10, True), fill=TEXT, anchor="lm")
    when = fmt_ago(t - last["time"]) + (f" · {last['server']}" if last.get("server") else "")
    d.text((W - 10, 100), when, font=font(9), fill=MUTED, anchor="rm")
    if sp.phase == "error":
        d.text((W // 2, 100), fit(d, f"échec : {sp.error}", font(9, True), 120), font=font(9, True),
               fill=HOT, anchor="mm")

    # historique : une paire de barres par test, le plus récent à droite
    panel(d, (6, 110, W - 6, 206), 8)
    d.text((14, 120), "HISTORIQUE", font=font(8, True), fill=MUTED, anchor="lm")
    hist = list(reversed(sp.history[:12]))
    top = max(max(r["down"] or 0, r["up"] or 0) for r in hist) or 1
    d.text((W - 14, 120), f"max {fmt_mbps(top)}", font=font(8), fill=MUTED, anchor="rm")
    x_left, x_right, base, height = 16, W - 16, 196, 62
    slot = (x_right - x_left) / max(len(hist), 6)
    bw = max(3, min(10, slot / 2 - 3))
    x = x_right - slot * len(hist)
    d.line((x_left, base, x_right, base), fill=TRACK)
    for i, r in enumerate(hist):
        cx = x + slot * (i + 0.5)
        newest = i == len(hist) - 1
        for j, (v, color) in enumerate(((r["down"], OK), (r["up"], ACCENT))):
            h = max(2, height * (v or 0) / top)
            bx = cx - bw - 1 + j * (bw + 2)
            fill = color if newest else dim(color, 0.6)
            d.rounded_rectangle((bx, base - h, bx + bw, base), min(2, bw / 2), fill=fill)
    d.text((x_left, 202), fmt_ago(t - hist[0]["time"]) if len(hist) > 1 else "", font=font(8),
           fill=dim(MUTED, 0.8), anchor="lm")
    d.text((x_right, 202), "dernier", font=font(8), fill=dim(MUTED, 0.8), anchor="rm")
    speed_button(d, 222, "lancer un test")


def speed_parts(v):
    """« 875 » et « Mb/s », ou « 1,25 » et « Gb/s »."""
    if v is None:
        return "—", ""
    if v >= 1000:
        return f"{v / 1000:.2f}".replace(".", ","), "Gb/s"
    return f"{v:.0f}", "Mb/s"


def speed_button(d, cy, text):
    """Bouton « OK … » centré, comme une touche."""
    f = font(10, True)
    w = d.textlength(text, font=f) + 44
    x0 = W // 2 - w / 2
    d.rounded_rectangle((x0, cy - 9, x0 + w, cy + 9), 9, outline=ACCENT, width=1)
    d.rounded_rectangle((x0 + 4, cy - 6, x0 + 28, cy + 6), 6, fill=ACCENT)
    d.text((x0 + 16, cy), "OK", font=font(8, True), fill=BG, anchor="mm")
    d.text((x0 + 34, cy), text, font=f, fill=ACCENT, anchor="lm")


# --- Menu Paramètres (touche Menu du G19) ------------------------------------------------------

def render_menu(menu, c, t=None):
    from .menu import VISIBLE

    apply_theme(c)
    t = t or time.time()
    img = canvas()
    d = ImageDraw.Draw(img)
    cfg = c.settings
    title_bar(d)
    d.text((8, 12), "Paramètres", font=font(14, True), fill=HEAD_TEXT, anchor="lm")
    d.text((W - 8, 12), "▲▼ choisir · OK changer · Menu fermer", font=font(9), fill=HEAD_MUTED,
           anchor="rm")
    rows = menu.items[menu.top:menu.top + VISIBLE]
    # surbrillance d'abord, à une position qui glisse vers la ligne choisie
    sy = glide("menu_cursor", 30 + (menu.index - menu.top) * 26, t)
    if _theme == "g19":   # barre de sélection bleue vernie, comme les menus du G19
        panel(d, (4, sy + 2, W - 4, sy + 24), 6, color=dim(ACCENT, 0.75))
    else:
        d.rounded_rectangle((4, sy + 2, W - 4, sy + 24), 6, fill=PANEL, outline=ACCENT, width=1)
    for i, item in enumerate(rows):
        key, label, kind, _opts = item
        y = 30 + i * 26
        idx = menu.top + i
        if kind == "title":
            d.text((10, y + 14), label.upper(), font=font(9, True), fill=ACCENT, anchor="lm")
            continue
        selected = idx == menu.index
        d.text((14, y + 13), fit(d, label, font(12, selected), 200), font=font(12, selected),
               fill=TEXT if selected else dim(TEXT, 0.8), anchor="lm")
        value = menu.value_text(item, cfg)
        if kind == "bool":
            on = bool(cfg.get(key))
            pw = 40
            d.rounded_rectangle((W - 14 - pw, y + 6, W - 14, y + 20), 7,
                                fill=OK if on else TRACK)
            knob = glide(f"menu_bool_{key}", W - 14 - 10 if on else W - 14 - pw + 10, t, 0.05)
            d.ellipse((knob - 5, y + 8, knob + 5, y + 18), fill=TEXT)
        else:
            d.text((W - 14, y + 13), (f"◄ {value} ►" if selected and kind in ("int", "choice")
                                      else value), font=font(12, True),
                   # sur la barre bleue pleine du thème G19, le bleu ne se lirait pas
                   fill=(TEXT if _theme == "g19" else ACCENT) if selected else TEXT, anchor="rm")
    # barre de défilement
    total = len(menu.items)
    if total > VISIBLE:
        h = (H - 34) * VISIBLE / total
        y0 = 30 + (H - 34) * menu.top / total
        d.rounded_rectangle((W - 4, y0, W - 2, y0 + h), 1, fill=TRACK)
    return postprocess(img)


# --- Météo -------------------------------------------------------------------------------------

SUN, MOON, CLOUD = DARK["SUN"], DARK["MOON"], DARK["CLOUD"]
CLOUD_DARK, RAIN, SNOW = DARK["CLOUD_DARK"], DARK["RAIN"], DARK["SNOW"]


def _cloud(d, cx, cy, s, color):
    """Nuage de largeur ~2s centré en (cx, cy)."""
    d.ellipse((cx - s, cy - s * 0.35, cx - s * 0.1, cy + s * 0.45), fill=color)
    d.ellipse((cx - s * 0.6, cy - s * 0.75, cx + s * 0.35, cy + s * 0.3), fill=color)
    d.ellipse((cx - s * 0.05, cy - s * 0.5, cx + s, cy + s * 0.45), fill=color)
    d.rectangle((cx - s * 0.55, cy, cx + s * 0.55, cy + s * 0.45), fill=color)


def _sun(d, cx, cy, r, day=True, bg=None):
    bg = bg or BG
    if not day:
        d.ellipse((cx - r, cy - r, cx + r, cy + r), fill=MOON)
        d.ellipse((cx - r * 0.35, cy - r * 1.05, cx + r * 1.4, cy + r * 0.6), fill=bg)
        return
    for i in range(8):
        a = i * math.pi / 4
        d.line((cx + math.cos(a) * r * 1.35, cy + math.sin(a) * r * 1.35,
                cx + math.cos(a) * r * 1.75, cy + math.sin(a) * r * 1.75), fill=SUN,
               width=max(1, int(r / 5)))
    d.ellipse((cx - r, cy - r, cx + r, cy + r), fill=SUN)


def weather_icon(d, code, cx, cy, size, day=True, bg=None):
    """Icône météo dessinée, d'environ `size` px de large."""
    from .weather import describe

    kind = describe(code)[1]
    s = size / 2
    if kind == "clear":
        _sun(d, cx, cy, s * 0.55, day, bg)
        return
    if kind == "partly":
        _sun(d, cx - s * 0.3, cy - s * 0.3, s * 0.42, day, bg)
        _cloud(d, cx + s * 0.15, cy + s * 0.2, s * 0.65, CLOUD)
        return
    if kind == "fog":
        for i in range(4):
            y = cy - s * 0.45 + i * s * 0.3
            off = s * 0.15 if i % 2 else 0
            d.rounded_rectangle((cx - s * 0.8 + off, y, cx + s * 0.8 - (s * 0.15 - off), y + s * 0.12),
                                2, fill=CLOUD)
        return
    dark = kind in ("rain", "storm", "snow", "drizzle")
    _cloud(d, cx, cy - s * 0.2, s * 0.75, CLOUD_DARK if kind == "storm" else
           (dim(CLOUD, 0.85) if dark else CLOUD))
    if kind in ("rain", "drizzle"):
        n = 2 if kind == "drizzle" else 3
        for i in range(n):
            x = cx - s * 0.4 + i * s * 0.4 + (s * 0.2 if n == 2 else 0)
            d.line((x, cy + s * 0.4, x - s * 0.12, cy + s * 0.75), fill=RAIN, width=max(1, int(s / 8)))
    elif kind == "snow":
        for i in range(3):
            x = cx - s * 0.4 + i * s * 0.4
            r = max(1.5, s * 0.09)
            d.ellipse((x - r, cy + s * 0.55 - r, x + r, cy + s * 0.55 + r), fill=SNOW)
    elif kind == "storm":
        d.polygon([(cx + s * 0.05, cy + s * 0.25), (cx - s * 0.2, cy + s * 0.6),
                   (cx, cy + s * 0.6), (cx - s * 0.12, cy + s * 0.9),
                   (cx + s * 0.25, cy + s * 0.48), (cx + s * 0.05, cy + s * 0.48)], fill=SUN)


def wind_arrow(d, cx, cy, deg, r, color):
    """Flèche dans le sens où souffle le vent (la météo donne la provenance)."""
    a = math.radians(deg + 90)  # 0° = vent du nord → flèche vers le bas
    tip = (cx + math.cos(a) * r, cy + math.sin(a) * r)
    left = (cx + math.cos(a + 2.5) * r, cy + math.sin(a + 2.5) * r)
    right = (cx + math.cos(a - 2.5) * r, cy + math.sin(a - 2.5) * r)
    d.polygon([tip, left, (cx, cy), right], fill=color)


def temp_color_air(v):
    return HOT if v >= 30 else WARN if v >= 22 else TEXT if v >= 5 else RAM_C


def page_weather(d, w, t):
    from .weather import describe

    cur = w.current() if w else None
    if not cur:
        status = w.status if w else "indisponible"
        d.text((W // 2, 100), "Météo", font=font(18, True), fill=ACCENT, anchor="mm")
        msg = {"init": "chargement…", "hors ligne": "pas de connexion"}.get(status, status)
        d.text((W // 2, 126), fit(d, msg, font(12), 290), font=font(12), fill=MUTED, anchor="mm")
        return

    day = bool(cur.get("is_day", 1))
    label = describe(cur["weather_code"])[0]
    weather_icon(d, cur["weather_code"], 46, 66, 62, day)
    temp = cur["temperature_2m"]
    d.text((86, 60), f"{temp:.0f}°", font=font(36, True), fill=temp_color_air(temp), anchor="lm")
    d.text((88, 88), fit(d, label, font(12, True), 120), font=font(12, True), fill=TEXT, anchor="lm")
    place = (w.place["name"] + (" (IP)" if w.place.get("ip") else "")) if w.place else ""
    d.text((10, 108), fit(d, f"{place} · ressenti {cur['apparent_temperature']:.0f}°",
                          font(10), 200), font=font(10), fill=MUTED, anchor="lm")

    # détails à droite
    x0, x1 = 214, 312
    days = w.days(5)
    rows = [("Humidité", f"{cur['relative_humidity_2m']:.0f} %"),
            ("Vent", f"{cur['wind_speed_10m']:.0f} km/h"),
            ("Pluie", f"{days[0][4]:.0f} %" if days and days[0][4] is not None else "—")]
    if days:
        rise, sset = days[0][5], days[0][6]
        rows.append(("Soleil", time.strftime("%H:%M", time.localtime(rise)) + "–" +
                     time.strftime("%H:%M", time.localtime(sset))))
    for i, (k, v) in enumerate(rows):
        y = 40 + i * 19
        d.text((x0, y), k, font=font(10), fill=MUTED, anchor="lm")
        room = x1 - x0 - d.textlength(k, font=font(10)) - 5
        d.text((x1, y), fit(d, v, font(11, True), room), font=font(11, True), fill=TEXT,
               anchor="rm")
    wind_arrow(d, x0 + 36, 59, cur.get("wind_direction_10m", 0), 5, ACCENT)

    # prochaines heures
    panel(d, (6, 120, W - 6, 172), 6)
    hours = w.hours(8)
    for i, (ts, tmp, pop, code, is_day) in enumerate(hours):
        cx = 6 + (W - 12) / len(hours) * (i + 0.5)
        hh = "maint." if i == 0 else time.strftime("%Hh", time.localtime(ts))
        d.text((cx, 128), hh, font=font(9), fill=MUTED, anchor="mm")
        weather_icon(d, code, cx, 144, 18, bool(is_day), PANEL)  # découpe de la lune sur le panneau
        d.text((cx, 162), f"{tmp:.0f}°", font=font(10, True), fill=TEXT, anchor="mm")
        if pop and pop >= 20:
            d.text((cx + 13, 134), f"{pop:.0f}%", font=font(7), fill=RAIN, anchor="mm")

    # 5 jours
    for i, (ts, code, tmax, tmin, pop, _rise, _set) in enumerate(days):
        cx = 6 + (W - 12) / len(days) * (i + 0.5)
        name = "Auj." if i == 0 else JOURS[time.localtime(ts).tm_wday].capitalize()
        d.text((cx, 184), name, font=font(10, True), fill=TEXT if i == 0 else MUTED, anchor="mm")
        weather_icon(d, code, cx, 203, 22)
        d.text((cx, 224), f"{tmax:.0f}°", font=font(11, True), fill=TEXT, anchor="rm")
        d.text((cx + 2, 224), f" {tmin:.0f}°", font=font(10), fill=MUTED, anchor="lm")


# --- VPN / Tailscale ---------------------------------------------------------------------------

TS_STATES = {"Running": "connecté", "Stopped": "arrêté", "Starting": "démarrage…",
             "NeedsLogin": "connexion requise", "NeedsMachineAuth": "appareil à approuver",
             "NoState": "indisponible"}


def tailscale_logo(d, x, y, on):
    """Grille 3×3 façon logo Tailscale (ligne du milieu pleine)."""
    for i in range(3):
        for j in range(3):
            full = j == 1 or (i == 1 and j == 2)
            color = (TEXT if on else MUTED) if full else dim(TEXT if on else MUTED, 0.35)
            cx, cy = x + i * 7, y + j * 7
            d.ellipse((cx - 2.5, cy - 2.5, cx + 2.5, cy + 2.5), fill=color)


def page_vpn(d, v, t):
    if not v:
        return
    ts = v.ts
    # carte Tailscale
    panel(d, (6, 28, W - 6, 88), 8)
    if not v.installed or ts is None:
        tailscale_logo(d, 18, 44, False)
        d.text((44, 50), "Tailscale", font=font(14, True), fill=TEXT, anchor="lm")
        d.text((44, 70), "non installé" if not v.installed else "service injoignable",
               font=font(11), fill=MUTED, anchor="lm")
    else:
        on = ts["running"]
        tailscale_logo(d, 18, 44, on)
        d.text((44, 44), "Tailscale", font=font(14, True), fill=TEXT, anchor="lm")
        label = v.message if v.busy or v.message else TS_STATES.get(ts["state"], ts["state"].lower())
        color = OK if on and not v.busy else WARN if v.busy or ts["state"].startswith("Needs") else MUTED
        tw = d.textlength("Tailscale", font=font(14, True))
        d.ellipse((50 + tw, 40, 58 + tw, 48), fill=color)
        d.text((62 + tw, 44), fit(d, label, font(11, True), W - 140 - tw), font=font(11, True),
               fill=color, anchor="lm")
        d.text((W - 14, 44), ts["ip"], font=font(12, True), fill=TEXT if on else MUTED, anchor="rm")
        line = f"{ts['host']} · {ts['tailnet']}"
        d.text((44, 62), fit(d, line, font(10), W - 60), font=font(10), fill=MUTED, anchor="lm")
        if ts["exit"]:
            exit_line = f"sortie via {ts['exit']}"
        else:
            exit_line = f"{ts['online']}/{len(ts['peers'])} en ligne · sans nœud de sortie"
        hint = "OK " + ("couper" if on else "connecter")
        room = W - 14 - d.textlength(hint, font=font(9, True)) - 8 - 44
        d.text((44, 77), fit(d, exit_line, font(10), room), font=font(10),
               fill=ACCENT if ts["exit"] else MUTED, anchor="lm")
        d.text((W - 14, 77), hint, font=font(9, True), fill=ACCENT, anchor="rm")

        # appareils
        for i, p in enumerate(ts["peers"][:5]):
            y = 98 + i * 18
            d.ellipse((12, y - 3, 18, y + 3), fill=OK if p["online"] else TRACK)
            name = fit(d, p["name"], font(11, True), 130)
            d.text((26, y), name, font=font(11, True), fill=TEXT if p["online"] else MUTED,
                   anchor="lm")
            d.text((30 + d.textlength(name, font=font(11, True)), y + 1), p["os"], font=font(9),
                   fill=MUTED, anchor="lm")
            if p["active"]:
                tag = "direct" if p["direct"] else "relais"
                d.text((214, y), tag, font=font(9, True), fill=OK if p["direct"] else WARN,
                       anchor="lm")
            right = p["ip"] if p["online"] else (f"vu {fmt_ago(p['seen'])}".replace("vu il y a", "il y a")
                                                 if p["seen"] else "hors ligne")
            d.text((W - 12, y), right, font=font(10), fill=MUTED, anchor="rm")
        if len(ts["peers"]) > 5:
            d.text((W - 12, 186), f"+{len(ts['peers']) - 5} appareils", font=font(9),
                   fill=dim(MUTED, 0.7), anchor="rm")
        if not ts["peers"]:
            tailscale_logo(d, W // 2 - 10, 118, False)
            d.text((W // 2, 150), "Aucun autre appareil sur ce réseau", font=font(11, True),
                   fill=MUTED, anchor="mm")
            d.text((W // 2, 167), "connecte un téléphone ou un PC à Tailscale" if on else
                   "OK pour connecter Tailscale", font=font(10), fill=dim(MUTED, 0.75),
                   anchor="mm")

    # IP publique + autres VPN
    d.line((6, 194, W - 6, 194), fill=TRACK)
    pub = v.public
    if pub:
        d.text((10, 206), "IP publique", font=font(9, True), fill=MUTED, anchor="lm")
        d.text((70, 206), pub["ip"], font=font(11, True), fill=TEXT, anchor="lm")
        where = " · ".join(x for x in (pub.get("isp"), pub.get("city")) if x)
        d.text((W - 10, 206), fit(d, where, font(10), 140), font=font(10), fill=MUTED, anchor="rm")
    x = 10
    others = [a for a in v.adapters if not a["name"].lower().startswith("tailscale")]
    for a in others[:3]:
        label = fit(d, a["name"].replace(" Adapter", "").replace(" Connect", ""), font(10), 120)
        w = d.textlength(label, font=font(10)) + 22
        panel(d, (x, 216, x + w, 232), 8)
        d.ellipse((x + 6, 221, x + 12, 227), fill=OK if a["up"] else TRACK)
        d.text((x + 16, 224), label, font=font(10), fill=TEXT if a["up"] else MUTED, anchor="lm")
        x += w + 6
    if not others:
        d.text((10, 224), "aucun autre VPN détecté", font=font(10), fill=dim(MUTED, 0.7), anchor="lm")


# --- Paroles -----------------------------------------------------------------------------------

LYRICS_OFFSET = 0.3   # s d'avance : la ligne s'affiche au moment où elle commence à être chantée


LYRICS_MOVE = 0.4        # s : la nouvelle ligne remonte à sa place


def page_lyrics(img, d, m, lyrics, t, animate=True):
    """Paroles ; animées (si `animate`) d'après la position dans le morceau : le bloc remonte
    en douceur quand une ligne commence."""
    from .lyrics import current_index

    if not m or not m.title:
        d.text((W // 2, 112), "Aucun morceau en cours", font=font(15, True), fill=MUTED, anchor="mm")
        return
    if m.bg:
        if _light():   # fond presque uni : les lignes estompées restent lisibles
            img.paste(Image.blend(m.bg, Image.new("RGB", m.bg.size, BG), 0.95), (0, 0))
        else:
            img.paste(backdrop(m.bg), (0, 0))
    fade_prev, fade_next = ((0.8, 0.15), (0.9, 0.12)) if _light() else         ((0.75, 0.25), (0.75, 0.17))
    # en-tête : mini pochette + titre
    if m.art:
        thumb = m.art.resize((30, 30), Image.LANCZOS)
        img.paste(thumb, (10, 30), thumb)
    d.text((48, 37), fit(d, m.title, font(12, True), W - 60), font=font(12, True), fill=TEXT,
           anchor="lm")
    d.text((48, 52), fit(d, m.artist, font(10), W - 60), font=font(10), fill=MUTED, anchor="lm")

    data = lyrics.get(m) if lyrics else None
    pos = m.position_at(t) + LYRICS_OFFSET
    if m.duration > 0:
        bar(d, 10, 232, W - 20, 3, min(pos / m.duration, 1), media_accent(m) if m.playing else MUTED)
    key_hints(d, 52, [("OK", "retour")], "right")

    def center(text, size=13):
        d.text((W // 2, 140), text, font=font(size, True), fill=MUTED, anchor="mm")

    if data == "loading":
        return center("recherche des paroles…")
    if not isinstance(data, dict):
        return center("Paroles introuvables")
    if data["instrumental"] and not data["synced"]:
        return center("♪ Instrumental ♪", 15)

    synced = data["synced"]
    if synced:
        i = current_index(synced, pos)
        cur = synced[i][1] if i >= 0 else ""
        start = synced[i][0] if i >= 0 else 0.0
        move = 1.0
        if animate and i >= 0:
            k = (pos - start) / LYRICS_MOVE
            move = 1 - (1 - min(1.0, max(0.0, k))) ** 3
        # tout le bloc est dessiné sur un calque, posé plus bas au début d'une ligne
        layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        d = ImageDraw.Draw(layer)
        # ligne en cours, mise en avant (taille réduite et jusqu'à 3 lignes si elle est longue,
        # jamais coupée) ; une ou deux lignes avant, estompées, et jusqu'à trois après
        lines_cur, size = fit_block(d, cur or "♪", W - 20, (17, 15, 13, 12), 3, True)
        lh = size + 5
        block = len(lines_cur) * lh
        y = 142 - block // 2 + lh // 2
        for k, line in enumerate(lines_cur):
            d.text((W // 2, y + k * lh), line, font=font(size, True), fill=TEXT, anchor="mm")
        top = y - lh // 2 - 12
        for j in (1, 2):
            if i - j >= 0 and synced[i - j][1] and top - (j - 1) * 17 > 72:
                text, sz = shrink_line(d, synced[i - j][1], W - 24, (11, 10, 9))
                d.text((W // 2, top - (j - 1) * 17), text, font=font(sz),
                       fill=dim(MUTED, fade_prev[0] - fade_prev[1] * j), anchor="mm")
        bottom = y + block - lh // 2 + 14
        for j in (1, 2, 3):
            yy = bottom + (j - 1) * 17
            if i + j < len(synced) and synced[i + j][1] and yy < H - 12:
                text, sz = shrink_line(d, synced[i + j][1], W - 24, (12, 11, 10, 9))
                d.text((W // 2, yy), text, font=font(sz),
                       fill=dim(TEXT, fade_next[0] - fade_next[1] * j), anchor="mm")
        shift = int(round((1 - move) * 20))
        clip = layer.crop((0, 0, W, H - 12 - shift))   # pas sur la barre de progression
        img.paste(clip, (0, shift), clip)
        return

    # paroles non synchronisées : on défile au prorata de la position dans le morceau
    plain = [l for l in data["plain"] if l.strip()]
    if not plain:
        return center("Paroles introuvables")
    start = int(len(plain) * (pos / m.duration)) if m.duration else 0
    for k, line in enumerate(plain[max(0, start - 1):start + 7]):
        text, sz = shrink_line(d, line, W - 24, (12, 11, 10, 9))
        d.text((W // 2, 80 + k * 19), text, font=font(sz),
               fill=TEXT if k == 1 else MUTED, anchor="mm")
    d.text((W - 10, 66), "non synchronisées", font=font(8), fill=dim(MUTED, 0.6), anchor="rm")


# --- Panneau ventilateurs (OK sur la page Système) ---------------------------------------------

FAN_CHIPS = [("auto", "Auto"), ("silent", "Silence"), ("balanced", "Équil."),
             ("performance", "Perf."), ("max", "Max")]
FAN_RPM_MAX = 3000


def render_fans(index, c, t=None):
    """Liste des ventilos avec leurs RPM, puis le choix du profil (curseur sur `index`)."""
    apply_theme(c)
    t = t or time.time()
    img = canvas()
    d = ImageDraw.Draw(img)
    fc = c.fans
    s = c.gpu.s if c.gpu else {}

    title_bar(d)
    d.text((8, 12), "Ventilateurs", font=font(14, True), fill=HEAD_TEXT, anchor="lm")
    temps = []
    if s.get("cpu_temp"):
        temps.append(f"CPU {s['cpu_temp']:.0f}°")
    if s.get("hotspot") or s.get("temp"):
        temps.append(f"GPU {s.get('hotspot') or s.get('temp'):.0f}°")
    d.text((W - 8, 12), "  ·  ".join(temps), font=font(11, True), fill=MUTED, anchor="rm")

    # la pompe n'est jamais pilotée : elle n'a rien à faire dans ce réglage
    readings = [f for f in (fc.readings if fc else []) if not f["pump"]]
    fans = [f for f in readings if f["rpm"] > 0 or f["gpu"]]
    hidden = len(readings) - len(fans)
    if not fans:
        msg = fc.error if fc and fc.error else "lecture des ventilateurs…"
        d.text((W // 2, 100), fit(d, msg, font(12), 290), font=font(12), fill=MUTED, anchor="mm")
    for i, f in enumerate(fans[:7]):
        y = 40 + i * 22
        on = f["rpm"] > 0
        name = (f["name"].replace("CPU Optional Fan", "CPU optionnel").replace("System Fan", "Système")
                .replace(" / Pump", ""))
        d.text((10, y), fit(d, name, font(11, True), 112), font=font(11, True),
               fill=TEXT if on else MUTED, anchor="lm")
        bar(d, 120, y - 3, 84, 6, f["rpm"] / FAN_RPM_MAX, (ACCENT if not f["gpu"] else GPU_C) if on else TRACK)
        d.text((246, y), f"{f['rpm']:.0f}" if on else "arrêt", font=font(11, True),
               fill=TEXT if on else MUTED, anchor="rm")
        d.text((249, y + 1), "tr/min" if on else "", font=font(8), fill=MUTED, anchor="lm")
        if f["gpu"]:
            tag, color = (f"{f['pct']:.0f}%" if f["pct"] is not None else "pilote"), GPU_C
        elif f["pct"] is not None:
            tag, color = f"{f['pct']:.0f}%", ACCENT
        else:
            tag, color = "auto", MUTED
        d.text((W - 8, y), tag, font=font(9, True), fill=color, anchor="rm")
    if hidden:
        d.text((10, 40 + min(len(fans), 7) * 22), f"{hidden} prise(s) sans ventilateur masquée(s)",
               font=font(8), fill=dim(MUTED, 0.6), anchor="lm")

    # choix du profil
    applied = fc.applied if fc else "auto"
    wanted = c.settings.get("fan_profile", "auto")
    cw, gap, x0, y0 = 58, 4, 7, 184
    for i, (pid, label) in enumerate(FAN_CHIPS):
        x = x0 + i * (cw + gap)
        selected, active = i == index, pid == applied
        d.rounded_rectangle((x, y0, x + cw, y0 + 24), 7,
                            fill=ACCENT if active else PANEL,
                            outline=TEXT if selected else (ACCENT if pid == wanted else TRACK),
                            width=2 if selected else 1)
        d.text((x + cw / 2, y0 + 12), label, font=font(11, True),
               fill=BG if active else (TEXT if selected else MUTED), anchor="mm")
    safety = getattr(fc, "safety", None) if fc else None
    if safety:
        # auto forcé par la chaleur : quand le profil choisi reviendra
        left = fc.recovery_left()
        label = dict(FAN_CHIPS).get(safety["profile"], safety["profile"])
        when = (f"retour à {label} dans {left:.0f} s" if left is not None
                else f"{label} reprendra une fois refroidi")
        d.text((W // 2, 226), f"Sécurité ({safety['reason']}) · {when}", font=font(9, True),
               fill=WARN, anchor="mm")
    else:
        key_hints(d, 226, [("◄►", "choisir"), ("OK", "appliquer"), ("Annuler", "")],
                  "center")
    return postprocess(img)


# --- Écran de démarrage ------------------------------------------------------------------------

def _chrome_fill(w, h, light):
    """Dégradé « chrome » : reflet clair en haut coupé net au milieu, remontée claire en bas."""
    col = Image.new("RGB", (1, h))
    split = h * 0.52
    for y in range(h):
        if y < split:
            c = mix((255, 255, 255), (168, 176, 188), y / split)
        else:
            c = mix((48, 54, 64), (196, 204, 214), (y - split) / max(1, h - split))
        if light:
            c = mix(c, (30, 36, 46), 0.55)
        col.putpixel((0, y), c)
    return col.resize((w, h))


def _ease(x):
    x = max(0.0, min(x, 1.0))
    return 1 - (1 - x) ** 3


def _gradient_text(img, xy, text, fnt, top, bottom):
    """Texte rempli d'un dégradé vertical (centré sur xy)."""
    box = ImageDraw.Draw(img).textbbox(xy, text, font=fnt, anchor="mm")
    w, h = box[2] - box[0] + 2, box[3] - box[1] + 2
    mask = Image.new("L", (w, h), 0)
    ImageDraw.Draw(mask).text((w / 2, h / 2), text, font=fnt, fill=255, anchor="mm")
    img.paste(_vgrad(w, h, top, bottom), (box[0], box[1]), mask)


BOOT_STEPS = ["Capteurs", "GPU", "Ventilateurs", "Média", "Discord", "Claude", "Steam",
              "Écran"]
_splash_bg = {}


def _ease_out(x):
    x = max(0.0, min(x, 1.0))
    return 1 - (1 - x) ** 3


def _keycap(w, h, accent):
    """Touche façon G-key : dessus bombé verni, flancs plus sombres, liseré de l'accent."""
    key = (w, h, accent, _theme)
    if key in _splash_bg:
        return _splash_bg[key]
    k = 3
    img = Image.new("RGBA", (w * k, h * k), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    light = _light()
    side_top, side_bot = ((214, 220, 228), (170, 178, 190)) if light else ((46, 50, 58), (14, 16, 20))
    face_top, face_bot = ((255, 255, 255), (228, 233, 240)) if light else ((70, 76, 86), (28, 31, 37))
    r = 16 * k
    # flancs (dégradé), puis dessus en retrait, puis reflet sur la moitié haute du dessus
    for y in range(h * k):
        c = mix(side_top, side_bot, y / (h * k))
        d.line((0, y, w * k, y), fill=c)
    mask = Image.new("L", (w * k, h * k), 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, w * k - 1, h * k - 1), r, fill=255)
    img.putalpha(mask)
    inset = 7 * k
    face = Image.new("RGB", (w * k - 2 * inset, h * k - 3 * inset))
    fd = ImageDraw.Draw(face)
    for y in range(face.height):
        fd.line((0, y, face.width, y), fill=mix(face_top, face_bot, y / face.height))
    fmask = Image.new("L", face.size, 0)
    ImageDraw.Draw(fmask).rounded_rectangle((0, 0, face.width - 1, face.height - 1), r - inset,
                                            fill=255)
    img.paste(face, (inset, inset // 2), fmask)
    gloss = Image.new("L", face.size, 0)
    ImageDraw.Draw(gloss).rounded_rectangle((0, 0, face.width - 1, face.height // 2), r - inset,
                                            fill=46 if not light else 0)
    img.paste((255, 255, 255), (inset, inset // 2), ImageChops.multiply(gloss, fmask))
    ImageDraw.Draw(img).rounded_rectangle((1, 1, w * k - 2, h * k - 2), r,
                                          outline=accent + (255,), width=k * 2)
    out = img.resize((w, h), Image.LANCZOS)
    _splash_bg[key] = out
    return out


def render_splash(progress, step, t, theme="dark", age=None, fade=1.0, version=""):
    """Écran de démarrage : une touche « G19 » vernie tombe en place et s'enfonce, sous un halo
    de l'accent ; dessous, le nom, une pastille par module (allumées avec le chargement) et une
    fine barre parcourue d'un reflet. `age` : secondes depuis l'apparition (None = sans
    animation d'entrée) ; `fade` : 1 → 0 pour le fondu de sortie."""
    set_theme(theme)
    a = 10.0 if age is None else age
    img = canvas()
    d = ImageDraw.Draw(img)
    cx = W // 2
    light = _light()

    # halo derrière la touche
    strength = 0 if _theme == "g15" else 35 if light else 60
    if strength:
        # halo doux qui s'éteint bien avant les bords (pas de cadre visible)
        glow = Image.radial_gradient("L").resize((260, 200), Image.BILINEAR)
        glow = glow.point(lambda v: max(0, 200 - v) * strength // 200)
        img.paste(ACCENT, (cx - 130, 92 - 100), glow)

    # touche : chute amortie, puis petit enfoncement
    kw, kh = 136, 92
    drop = (1 - _ease_out(a / 0.55)) * -40
    press = 3 if 0.6 < a < 0.78 else 0
    ky = int(46 + drop + press)
    shadow = Image.new("L", (kw + 60, 60), 0)       # marge : le flou ne bute pas sur les bords
    ImageDraw.Draw(shadow).ellipse((20, 18, kw + 39, 41), fill=90 if not light else 50)
    shadow = shadow.filter(ImageFilter.GaussianBlur(7))
    img.paste((0, 0, 0), (cx - kw // 2 - 30, 46 + kh - 28), shadow)
    cap = _keycap(kw, kh, ACCENT)
    img.paste(cap, (cx - kw // 2, ky), cap)
    face_cy = ky + kh // 2 - 4
    _gradient_text(img, (cx, face_cy - 4), "G19", font(34, True),
                   mix(ACCENT, (255, 255, 255), 0.35) if not light else mix(ACCENT, (0, 0, 0), 0.1),
                   ACCENT if not light else mix(ACCENT, (0, 0, 0), 0.35))
    d.text((cx, face_cy + 20), "M O N I T O R", font=font(7, True),
           fill=MUTED if not light else mix(TEXT, PANEL, 0.4), anchor="mm")

    # nom
    k = _ease_out((a - 0.5) / 0.5)
    if k > 0:
        d.text((cx, 164), "PC Monitor", font=font(15, True), fill=mix(BG, TEXT, k), anchor="mm")

    # une pastille par module, allumée selon l'avancement (celle en cours pulse)
    n = len(BOOT_STEPS)
    done = progress * n
    gap = 22
    x0 = cx - (n - 1) * gap / 2
    for i in range(n):
        x = x0 + i * gap
        if i + 1 <= done:
            c, r = ACCENT, 4
        elif i < done + 1:
            c, r = mix(TRACK, ACCENT, 0.5 + 0.5 * math.sin(t * 8)), 4
        else:
            c, r = TRACK, 3
        d.ellipse((x - r, 188 - r, x + r, 188 + r), fill=c)
    d.text((cx, 203), step or "", font=font(9), fill=MUTED, anchor="mm")

    # barre fine avec reflet qui la parcourt
    bx0, bx1, by = 70, W - 70, 218
    d.rounded_rectangle((bx0, by, bx1, by + 4), 2, fill=TRACK)
    fw = int((bx1 - bx0) * max(0.0, min(progress, 1.0)))
    if fw > 4:
        d.rounded_rectangle((bx0, by, bx0 + fw, by + 4), 2, fill=ACCENT)
        sx = bx0 + (t * 160) % (fw + 40) - 20
        for dx in range(-14, 15):
            x = sx + dx
            if bx0 <= x <= bx0 + fw:
                f = 1 - abs(dx) / 14
                d.line((x, by, x, by + 4), fill=mix(ACCENT, (255, 255, 255), 0.6 * f))
    d.text((W - 8, H - 4), time.strftime("%H:%M", time.localtime(t)), font=font(8),
           fill=dim(MUTED, 0.7), anchor="rb")
    if version:                             # commit en cours, en bas à gauche
        d.text((8, H - 4), f"version {version}", font=font(8), fill=dim(MUTED, 0.7), anchor="lb")

    if age is not None and age < 0.35:      # fondu d'entrée
        img = Image.blend(Image.new("RGB", (W, H), (0, 0, 0)), img, max(0.0, age / 0.35))
    if fade < 1:                            # fondu de sortie
        img = Image.blend(Image.new("RGB", (W, H), (0, 0, 0)), img, max(0.0, fade))
    return postprocess(img)


# --- Récapitulatif de fin de partie -------------------------------------------------------------

RECAP_SECONDS = 20


def render_recap(c, rec, t, shown_at):
    """Écran affiché quand une partie se termine : durée, FPS, températures, consommation,
    courbe des FPS ; se ferme tout seul (barre en bas) ou avec n'importe quelle touche."""
    apply_theme(c)
    img = canvas()
    games = c.games
    bg = games.image(rec, "bg") if games else None
    if bg:
        img.paste(backdrop(bg), (0, 0))
    d = ImageDraw.Draw(img)
    title_bar(d)
    d.text((8, 12), "Fin de partie", font=font(14, True), fill=HEAD_TEXT, anchor="lm")
    d.text((W - 8, 12), "une touche pour fermer", font=font(9), fill=HEAD_MUTED, anchor="rm")

    cover = games.image(rec, "cover") if games else None
    if cover:
        img.paste(cover, (8, 30), cover)
    else:
        placeholder_cover(d, (8, 30, 92, 156), rec.get("name") or "?")
    x, maxw = 102, W - 102 - 8
    y = 28
    for line in wrap(d, rec.get("name") or "?", font(15, True), maxw, 2):
        d.text((x, y), line, font=font(15, True), fill=TEXT)
        y += 19
    d.text((x, 70), "SESSION" + (f" · {rec['launcher'].upper()}" if rec.get("launcher") else ""),
           font=font(9, True), fill=CLAUDE)
    d.text((x, 80), fmt_duration(rec.get("duration") or 0), font=font(22, True), fill=TEXT)
    if games:
        total, _src = games.total_seconds(rec)
        line = f"aujourd'hui {fmt_duration(games.today_seconds(t))} · total {fmt_hours(total)}"
        d.text((x, 110), fit(d, line, font(11), maxw), font=font(11), fill=MUTED)

    def val(key, fmt="{:.0f}", suffix=""):
        v = rec.get(key)
        return "—" if v is None else fmt.format(v) + suffix

    cw = (maxw - 8) / 3
    chip(d, x, 128, cw, "FPS moy.", val("fps_avg"))
    chip(d, x + cw + 4, 128, cw, "1% low", val("fps_low1"))
    chip(d, x + 2 * (cw + 4), 128, cw, "FPS max", val("fps_max"))
    cw2 = (W - 12 - 8) / 3
    gpu_t, cpu_t = rec.get("temp_max"), rec.get("cpu_temp_max")
    chip(d, 6, 162, cw2, "GPU max", val("temp_max", suffix="°"),
         temp_color(gpu_t) if gpu_t else TEXT)
    chip(d, 6 + cw2 + 4, 162, cw2, "CPU max", val("cpu_temp_max", suffix="°"),
         temp_color(cpu_t) if cpu_t else TEXT)
    chip(d, 6 + 2 * (cw2 + 4), 162, cw2, "GPU moy.", val("power_avg", suffix=" W"))

    curve = rec.get("fps_curve") or []
    panel(d, (6, 196, W - 6, 232), 5)
    d.text((12, 200), "FPS", font=font(9, True), fill=MUTED)
    if len(curve) >= 2:
        sparkline(d, 36, 199, W - 48, 30, curve, ACCENT, vmax=max(curve) * 1.15, panel=None)
    # temps restant avant fermeture automatique
    left = max(0.0, 1 - (t - shown_at) / RECAP_SECONDS)
    d.rectangle((0, H - 3, int(W * left), H - 1), fill=ACCENT)
    return postprocess(img)


# --- PC au repos -------------------------------------------------------------------------------

AWAY_COLORS = {"discord": "DISCORD", "claude": "CLAUDE", "steam": "STEAM_BLUE"}
AWAY_ORDER = ["Alerte", "Streaming", "Docker", "Claude", "Discord", "Vocal", "Steam", "Système", "Batterie",
              "Périphérique", "Média"]


def away_color(item):
    col = item.get("color")
    return globals()[AWAY_COLORS[col]] if isinstance(col, str) else col or ACCENT


def fmt_away(sec):
    sec = int(sec)
    return f"{sec // 3600} h {sec % 3600 // 60:02d}" if sec >= 3600 else f"{max(1, sec // 60)} min"


def render_idle(c, t):
    """PC verrouillé ou inactif : grande horloge, météo, et ce qui est arrivé entre-temps."""
    apply_theme(c)
    img = canvas()
    d = ImageDraw.Draw(img)
    away = c.away
    lt = time.localtime(t)
    d.text((W // 2, 74), time.strftime("%H:%M", lt), font=font(72, True), fill=TEXT, anchor="mm")
    sec_w = 120 * (lt.tm_sec + t % 1) / 60
    d.rounded_rectangle((W // 2 - 60, 116, W // 2 + 60, 118), 1, fill=TRACK)
    d.rounded_rectangle((W // 2 - 60, 116, W // 2 - 60 + sec_w, 118), 1, fill=ACCENT)
    date = f"{JOURS[lt.tm_wday].capitalize()} {lt.tm_mday} {MOIS[lt.tm_mon - 1]}"
    d.text((W // 2, 134), date, font=font(15), fill=MUTED, anchor="mm")

    cur = c.weather.current() if c.weather else None
    if cur:
        from .weather import describe
        temp = f"{cur['temperature_2m']:.0f}°"
        label = describe(cur["weather_code"])[0]
        f1, f2 = font(18, True), font(12)
        w = 30 + d.textlength(temp, font=f1) + 8 + d.textlength(label, font=f2)
        x = W // 2 - w / 2
        weather_icon(d, cur["weather_code"], x + 12, 162, 26, bool(cur.get("is_day", 1)))
        d.text((x + 30, 162), temp, font=f1, fill=temp_color_air(cur["temperature_2m"]),
               anchor="lm")
        d.text((x + 38 + d.textlength(temp, font=f1), 163), label, font=f2, fill=MUTED,
               anchor="lm")

    counts = away.counts() if away else {}
    y0 = 196
    panel(d, (6, y0, W - 6, 232), 6)
    if not counts:
        state = "verrouillé" if away and away.locked else "au repos"
        since = f" depuis {fmt_away(t - away.since)}" if away and away.active else ""
        d.text((W // 2, 214), f"PC {state}{since} · rien de nouveau", font=font(11),
               fill=MUTED, anchor="mm")
    else:
        chips = sorted(counts.items(), key=lambda kv: AWAY_ORDER.index(kv[0])
                       if kv[0] in AWAY_ORDER else 99)
        first = {it["source"]: it for it in away.items}
        x = 14
        for src, n in chips:
            col = away_color(first[src])
            text = fit(d, f"{src} {n}", font(11, True), 140)   # nom d'appli : une ligne
            w = d.textlength(text, font=font(11, True)) + 18
            if x + w > W - 12:
                d.text((W - 14, 214), "…", font=font(12, True), fill=MUTED, anchor="rm")
                break
            d.ellipse((x, 210, x + 8, 218), fill=col)
            d.text((x + 12, 214), text, font=font(11, True), fill=TEXT, anchor="lm")
            x += w
    n = current_toast(c, None, t)
    if n:
        slide_toast(img, n, c.discord.avatars if c.discord else None, t,
                    c.settings["toast_seconds"])
    return postprocess(img)


def away_lines(items):
    """Regroupe les événements : un auteur Discord = une ligne, avec le nombre de messages."""
    lines, index = [], {}
    for it in items:
        key = (it["source"], it["title"]) if it["source"] in ("Discord", "Vocal") else id(it)
        if key in index:
            line = index[key]
            line["count"] += 1
            line["body"] = it["body"]
            continue
        line = index[key] = {**it, "count": 1}
        lines.append(line)
    order = {s: i for i, s in enumerate(AWAY_ORDER)}
    lines.sort(key=lambda ln: order.get(ln["source"], 99))
    return lines


def render_away(c, summary, t):
    """Au retour : tout ce qui est arrivé pendant l'absence ; une touche pour fermer."""
    from .away import SUMMARY_SECONDS

    apply_theme(c)
    img = canvas()
    d = ImageDraw.Draw(img)
    items, since, until, shown_at = summary
    title_bar(d)
    d.text((8, 12), f"Pendant ton absence · {fmt_away(until - since)}", font=font(13, True),
           fill=HEAD_TEXT, anchor="lm")
    d.text((W - 8, 12), "une touche pour fermer", font=font(9), fill=HEAD_MUTED, anchor="rm")
    lines = away_lines(items)
    rows = 6
    cache = c.discord.avatars if c.discord else None
    for i, ln in enumerate(lines[:rows]):
        y = 30 + i * 33
        col = away_color(ln)
        panel(d, (6, y, W - 6, y + 29), 5)
        d.rounded_rectangle((6, y, 9, y + 29), 2, fill=col)
        x = 16
        if ln.get("icon"):
            avatar(img, d, cache, ln["icon"], 29, y + 14, 22, ln["title"], color=col)
            x = 46
        src = fit(d, ln["source"].upper(), font(9, True), 150) +             (f" · {ln['count']}" if ln["count"] > 1 else "")
        d.text((x, y + 8), src, font=font(9, True), fill=col, anchor="lm")
        stamp = time.strftime("%H:%M", time.localtime(ln["at"]))
        d.text((W - 12, y + 8), stamp, font=font(9), fill=MUTED, anchor="rm")
        line = f"{ln['title']} · {ln['body']}" if ln.get("body") else ln["title"]
        d.text((x, y + 21), fit(d, line, font(11, True), W - x - 14), font=font(11, True),
               fill=TEXT, anchor="lm")
    if len(lines) > rows:
        d.text((W - 10, 232), f"+{len(lines) - rows} autres", font=font(9), fill=MUTED,
               anchor="rb")
    left = max(0.0, 1 - (t - shown_at) / SUMMARY_SECONDS)
    d.rectangle((0, H - 3, int(W * left), H - 1), fill=ACCENT)
    return postprocess(img)


# en fin de module : looks.py lit les couleurs et fonctions ci-dessus au moment du dessin
from . import looks  # noqa: E402
