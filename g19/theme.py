"""Thèmes tkinter de l'utilitaire (config_g19.pyw), calqués sur ceux de l'écran du G19 :
sombre, clair et « G19 » (chrome et bleu façon 2010). `apply()` peut être rappelé à chaud :
les styles ttk sont refaits et les widgets tk inscrits avec `paint()` sont recolorés."""
import ctypes
import tkinter as tk
from tkinter import font as tkfont
from tkinter import ttk

from PIL import Image, ImageDraw, ImageTk


def hexa(c):
    return "#%02x%02x%02x" % c


def _mix(a, b, f):
    return tuple(int(x + (y - x) * f) for x, y in zip(a, b))


PALETTES = {
    "dark": {"BG": (8, 11, 16), "PANEL": (22, 28, 36), "FIELD": (30, 37, 47),
             "TRACK": (52, 62, 76), "HOVER": (44, 54, 66), "TEXT": (240, 243, 247),
             "MUTED": (150, 160, 172), "ACCENT": (70, 220, 230), "ON_ACCENT": (6, 18, 22),
             "OK": (90, 220, 120), "CLAUDE": (240, 135, 100), "HEAD": ((30, 38, 49), (16, 21, 28)),
             "DARK_TITLE": True},
    "light": {"BG": (233, 237, 242), "PANEL": (255, 255, 255), "FIELD": (244, 246, 249),
              "TRACK": (204, 212, 221), "HOVER": (226, 232, 239), "TEXT": (28, 33, 40),
              "MUTED": (96, 105, 115), "ACCENT": (0, 124, 138), "ON_ACCENT": (255, 255, 255),
              "OK": (26, 140, 60), "CLAUDE": (200, 95, 60),
              "HEAD": ((255, 255, 255), (232, 237, 243)), "DARK_TITLE": False},
    "g19": {"BG": (2, 4, 7), "PANEL": (18, 21, 26), "FIELD": (9, 12, 16),
            "TRACK": (48, 53, 61), "HOVER": (58, 64, 73), "TEXT": (232, 236, 240),
            "MUTED": (150, 158, 168), "ACCENT": (0, 168, 240), "ON_ACCENT": (255, 255, 255),
            "OK": (110, 214, 90), "CLAUDE": (240, 135, 100), "HEAD": "chrome",
            "DARK_TITLE": True},
    # rétro G15 : tout en ambre sur fond brun très sombre
    "g15": {"BG": (10, 6, 0), "PANEL": (26, 16, 2), "FIELD": (16, 10, 1),
            "TRACK": (74, 46, 6), "HOVER": (96, 60, 8), "TEXT": (255, 186, 40),
            "MUTED": (176, 118, 20), "ACCENT": (255, 160, 0), "ON_ACCENT": (20, 12, 0),
            "OK": (255, 200, 80), "CLAUDE": (255, 170, 60),
            "HEAD": ((48, 30, 4), (18, 11, 1)), "DARK_TITLE": True},
    "neon": {"BG": (9, 3, 20), "PANEL": (24, 10, 44), "FIELD": (16, 6, 32),
             "TRACK": (62, 32, 96), "HOVER": (80, 42, 120), "TEXT": (248, 240, 255),
             "MUTED": (176, 150, 206), "ACCENT": (0, 238, 255), "ON_ACCENT": (10, 2, 24),
             "OK": (60, 255, 170), "CLAUDE": (255, 130, 90),
             "HEAD": ((44, 12, 72), (14, 4, 30)), "DARK_TITLE": True},
}
PALETTES["dynamic"] = PALETTES["dark"]   # l'utilitaire garde la palette sombre
PALETTES.update({
    "contrast": {"BG": (0, 0, 0), "PANEL": (20, 20, 20), "FIELD": (10, 10, 10),
                 "TRACK": (90, 90, 90), "HOVER": (54, 54, 54), "TEXT": (255, 255, 255),
                 "MUTED": (215, 215, 215), "ACCENT": (255, 222, 0), "ON_ACCENT": (0, 0, 0),
                 "OK": (0, 255, 110), "CLAUDE": (255, 150, 100),
                 "HEAD": ((30, 30, 30), (6, 6, 6)), "DARK_TITLE": True},
    "glacier": {"BG": (13, 19, 27), "PANEL": (27, 37, 49), "FIELD": (20, 28, 38),
                "TRACK": (62, 78, 97), "HOVER": (44, 58, 75), "TEXT": (236, 242, 248),
                "MUTED": (164, 182, 200), "ACCENT": (130, 210, 245), "ON_ACCENT": (8, 22, 32),
                "OK": (130, 226, 170), "CLAUDE": (246, 164, 134),
                "HEAD": ((36, 49, 64), (18, 26, 36)), "DARK_TITLE": True},
    "braise": {"BG": (14, 7, 4), "PANEL": (36, 19, 12), "FIELD": (24, 12, 7),
               "TRACK": (88, 50, 32), "HOVER": (66, 36, 22), "TEXT": (255, 242, 230),
               "MUTED": (210, 176, 154), "ACCENT": (255, 146, 42), "ON_ACCENT": (28, 10, 0),
               "OK": (178, 226, 92), "CLAUDE": (255, 170, 120),
               "HEAD": ((52, 26, 14), (20, 9, 5)), "DARK_TITLE": True},
    # terminal : vert phosphore sur noir
    "terminal": {"BG": (2, 8, 3), "PANEL": (8, 22, 10), "FIELD": (4, 14, 6),
                 "TRACK": (22, 66, 30), "HOVER": (16, 46, 22), "TEXT": (150, 255, 160),
                 "MUTED": (84, 180, 96), "ACCENT": (60, 255, 110), "ON_ACCENT": (0, 18, 4),
                 "OK": (120, 255, 140), "CLAUDE": (170, 255, 150),
                 "HEAD": ((12, 34, 16), (3, 12, 5)), "DARK_TITLE": True},
    "aero": {"BG": (10, 26, 44), "PANEL": (26, 48, 72), "FIELD": (18, 36, 56),
             "TRACK": (70, 98, 128), "HOVER": (40, 66, 94), "TEXT": (255, 255, 255),
             "MUTED": (200, 218, 236), "ACCENT": (120, 206, 255), "ON_ACCENT": (6, 24, 40),
             "OK": (120, 232, 120), "CLAUDE": (240, 140, 100),
             "HEAD": ((60, 110, 160), (20, 44, 72)), "DARK_TITLE": True},
    "analog": {"BG": (22, 20, 18), "PANEL": (42, 37, 32), "FIELD": (32, 28, 24),
               "TRACK": (84, 74, 62), "HOVER": (60, 53, 46), "TEXT": (246, 238, 222),
               "MUTED": (196, 182, 160), "ACCENT": (226, 176, 86), "ON_ACCENT": (30, 22, 8),
               "OK": (156, 206, 112), "CLAUDE": (238, 152, 112),
               "HEAD": ((64, 54, 40), (30, 26, 22)), "DARK_TITLE": True},
    "hud": {"BG": (0, 6, 2), "PANEL": (0, 18, 7), "FIELD": (0, 12, 4),
            "TRACK": (22, 72, 36), "HOVER": (10, 40, 18), "TEXT": (160, 255, 178),
            "MUTED": (96, 196, 116), "ACCENT": (120, 255, 150), "ON_ACCENT": (0, 20, 6),
            "OK": (120, 255, 150), "CLAUDE": (255, 172, 112),
            "HEAD": ((0, 30, 12), (0, 8, 3)), "DARK_TITLE": True},
    "tron": {"BG": (0, 4, 10), "PANEL": (0, 16, 28), "FIELD": (0, 10, 18),
             "TRACK": (0, 62, 86), "HOVER": (0, 34, 52), "TEXT": (224, 250, 255),
             "MUTED": (136, 196, 216), "ACCENT": (0, 232, 255), "ON_ACCENT": (0, 18, 26),
             "OK": (64, 255, 192), "CLAUDE": (255, 152, 92),
             "HEAD": ((0, 30, 46), (0, 8, 16)), "DARK_TITLE": True},
    "paper": {"BG": (240, 233, 216), "PANEL": (250, 246, 234), "FIELD": (255, 252, 244),
              "TRACK": (196, 186, 166), "HOVER": (232, 224, 204), "TEXT": (28, 26, 24),
              "MUTED": (84, 76, 66), "ACCENT": (26, 70, 140), "ON_ACCENT": (255, 255, 255),
              "OK": (36, 110, 56), "CLAUDE": (180, 80, 40),
              "HEAD": ((252, 248, 238), (232, 224, 206)), "DARK_TITLE": False},
    "paper_dark": {"BG": (30, 29, 32), "PANEL": (44, 42, 44), "FIELD": (36, 34, 37),
                   "TRACK": (92, 86, 80), "HOVER": (60, 57, 58), "TEXT": (240, 234, 220),
                   "MUTED": (184, 176, 162), "ACCENT": (130, 178, 236), "ON_ACCENT": (16, 20, 30),
                   "OK": (136, 210, 146), "CLAUDE": (238, 152, 112),
                   "HEAD": ((52, 50, 52), (32, 31, 34)), "DARK_TITLE": True},
    "xp": {"BG": (236, 233, 216), "PANEL": (255, 255, 255), "FIELD": (255, 255, 255),
           "TRACK": (127, 157, 185), "HOVER": (225, 235, 250), "TEXT": (0, 0, 0),
           "MUTED": (80, 80, 80), "ACCENT": (0, 84, 227), "ON_ACCENT": (255, 255, 255),
           "OK": (30, 150, 30), "CLAUDE": (196, 90, 50),
           "HEAD": ((0, 88, 238), (0, 61, 174)), "DARK_TITLE": False},
    "symbian": {"BG": (4, 20, 52), "PANEL": (16, 50, 104), "FIELD": (10, 34, 78),
                "TRACK": (40, 80, 140), "HOVER": (28, 70, 130), "TEXT": (255, 255, 255),
                "MUTED": (170, 196, 230), "ACCENT": (56, 170, 255), "ON_ACCENT": (2, 16, 40),
                "OK": (110, 230, 90), "CLAUDE": (255, 160, 110),
                "HEAD": ((50, 130, 220), (10, 50, 128)), "DARK_TITLE": True},
    "pixel": {"BG": (12, 12, 28), "PANEL": (36, 36, 76), "FIELD": (24, 24, 52),
              "TRACK": (76, 76, 124), "HOVER": (52, 52, 100), "TEXT": (252, 252, 252),
              "MUTED": (188, 188, 204), "ACCENT": (60, 188, 252), "ON_ACCENT": (12, 12, 28),
              "OK": (88, 216, 84), "CLAUDE": (252, 160, 68),
              "HEAD": ((52, 52, 104), (24, 24, 56)), "DARK_TITLE": True},
    # rouge nuit : tout en rouge sur noir
    "red": {"BG": (4, 0, 0), "PANEL": (22, 2, 2), "FIELD": (12, 1, 1),
            "TRACK": (70, 8, 8), "HOVER": (48, 6, 6), "TEXT": (255, 90, 80),
            "MUTED": (190, 56, 50), "ACCENT": (255, 50, 40), "ON_ACCENT": (20, 0, 0),
            "OK": (255, 110, 90), "CLAUDE": (255, 120, 100),
            "HEAD": ((40, 4, 4), (10, 1, 1)), "DARK_TITLE": True},
})

FONT = ("Segoe UI", 10)
NAME = "dark"
# couleurs du thème en cours, en "#rrggbb" (lues par l'utilitaire au moment du dessin)
BG_ = PANEL_ = FIELD_ = TRACK_ = HOVER_ = TEXT_ = MUTED_ = ACCENT_ = ON_ACCENT_ = OK_ = \
    CLAUDE_ = "#000000"

_painted = []          # (widget, {option: clé de palette})
_images = []           # images des interrupteurs (gardées en vie pour Tk)
_switch_n = [0]


def _set_globals(name):
    global NAME, BG_, PANEL_, FIELD_, TRACK_, HOVER_, TEXT_, MUTED_, ACCENT_, ON_ACCENT_, OK_, \
        CLAUDE_
    NAME = name if name in PALETTES else "dark"
    p = PALETTES[NAME]
    BG_, PANEL_, FIELD_, TRACK_, HOVER_, TEXT_, MUTED_, ACCENT_, ON_ACCENT_, OK_, CLAUDE_ = (
        hexa(p[k]) for k in ("BG", "PANEL", "FIELD", "TRACK", "HOVER", "TEXT", "MUTED", "ACCENT",
                             "ON_ACCENT", "OK", "CLAUDE"))


_set_globals("dark")


def color(key):
    return hexa(PALETTES[NAME][key])


def paint(widget, **opts):
    """Inscrit un widget tk (non ttk) pour qu'il suive le thème : paint(w, bg="PANEL")."""
    _painted.append((widget, opts))
    widget.configure(**{o: color(k) for o, k in opts.items()})
    return widget


def header_image(width, height):
    """Fond du bandeau : chrome brossé avec liseré bleu (G19), dégradé discret sinon."""
    p = PALETTES[NAME]
    img = Image.new("RGB", (width, height))
    d = ImageDraw.Draw(img)
    if p["HEAD"] == "chrome":
        split = height * 0.48
        for y in range(height):
            if y < split:
                c = _mix((122, 128, 138), (78, 83, 92), y / split)
            else:
                c = _mix((42, 46, 53), (16, 18, 22), (y - split) / (height - split))
            d.line((0, y, width, y), fill=c)
        d.line((0, 0, width, 0), fill=(168, 174, 184))
        d.line((0, height - 2, width, height - 2), fill=p["ACCENT"], width=2)
    else:
        top, bottom = p["HEAD"]
        for y in range(height):
            d.line((0, y, width, y), fill=_mix(top, bottom, y / max(1, height - 1)))
        if NAME == "neon":       # liseré dégradé magenta → cyan
            for x in range(width):
                d.line((x, height - 2, x, height - 1),
                       fill=_mix((255, 64, 200), p["ACCENT"], x / max(1, width - 1)))
        else:
            d.line((0, height - 2, width, height - 2), fill=p["ACCENT"], width=2)
    return img


class HeaderBar(tk.Canvas):
    """Bandeau du haut : logo, titre, sous-titre, état de l'appli à droite ; suit le thème."""

    def __init__(self, master, title, subtitle, height=52):
        super().__init__(master, height=height, highlightthickness=0, bd=0)
        self._title, self._subtitle, self._h = title, subtitle, height
        self._state = ("…", None)
        self._photo = None
        self.bind("<Configure>", lambda e: self.redraw())

    def set_state(self, text, color_key=None):
        if (text, color_key) != self._state:
            self._state = (text, color_key)
            self.redraw()

    def redraw(self):
        w = max(self.winfo_width(), 200)
        self.delete("all")
        self._photo = ImageTk.PhotoImage(header_image(w, self._h))
        self.create_image(0, 0, image=self._photo, anchor="nw")
        chrome = PALETTES[NAME]["HEAD"] == "chrome"
        title_fg = "#ffffff" if chrome else TEXT_
        sub_fg = "#c8ced8" if chrome else MUTED_
        cy = self._h // 2 - 1
        # pastille « G19 » façon touche
        self.create_rectangle(14, cy - 13, 54, cy + 13, fill=ACCENT_, outline="")
        self.create_text(34, cy, text="G19", fill=ON_ACCENT_, font=("Segoe UI", 11, "bold"))
        title_font = tkfont.Font(family="Segoe UI", size=15, weight="bold")
        self.create_text(66, cy - 1, text=self._title, anchor="w", fill=title_fg, font=title_font)
        tw = 66 + title_font.measure(self._title) + 10
        self.create_text(tw, cy + 2, text=self._subtitle, anchor="w", fill=sub_fg,
                         font=("Segoe UI", 10))
        text, key = self._state
        fg = color(key) if key else (sub_fg if chrome else MUTED_)
        self.create_text(w - 16, cy, text=text, anchor="e", fill=fg,
                         font=("Segoe UI", 10, "bold"))


def _switch_images(root):
    """Interrupteurs (pilule + bouton rond), dessinés en grand puis réduits (lissés)."""
    p = PALETTES[NAME]
    w, h, k = 36, 20, 4

    def pill(track, knob, on):
        img = Image.new("RGBA", (w * k, h * k), (0, 0, 0, 0))
        d = ImageDraw.Draw(img)
        d.rounded_rectangle((0, 0, w * k - 1, h * k - 1), h * k // 2, fill=track)
        r = (h - 6) * k // 2
        cx = (w - h // 2) * k if on else h // 2 * k
        d.ellipse((cx - r, h * k // 2 - r, cx + r, h * k // 2 + r), fill=knob)
        return ImageTk.PhotoImage(img.resize((w, h), Image.LANCZOS), master=root)

    off = pill(p["TRACK"] + (255,), _mix(p["MUTED"], p["TEXT"], 0.4) + (255,), False)
    on = pill(p["ACCENT"] + (255,), p["ON_ACCENT"] + (255,) if NAME != "light"
              else (255, 255, 255, 255), True)
    off_hover = pill(p["HOVER"] + (255,), p["TEXT"] + (255,), False)
    _images[:] = [off, on, off_hover]
    return off, on, off_hover


def titlebar(root):
    """Barre de titre Windows assortie : sombre ou claire, couleur de légende (Windows 11)."""
    try:
        root.update_idletasks()
        hwnd = ctypes.windll.user32.GetParent(root.winfo_id())
        dwm = ctypes.windll.dwmapi
        p = PALETTES[NAME]
        on = ctypes.c_int(1 if p["DARK_TITLE"] else 0)
        dwm.DwmSetWindowAttribute(hwnd, 20, ctypes.byref(on), 4)   # DWMWA_USE_IMMERSIVE_DARK_MODE
        head = p["HEAD"]
        r, g, b = (78, 83, 92) if head == "chrome" else head[0]
        caption = ctypes.c_int(r | g << 8 | b << 16)
        dwm.DwmSetWindowAttribute(hwnd, 35, ctypes.byref(caption), 4)  # DWMWA_CAPTION_COLOR
        tr, tg, tb = (255, 255, 255) if p["DARK_TITLE"] else p["TEXT"]
        text = ctypes.c_int(tr | tg << 8 | tb << 16)
        dwm.DwmSetWindowAttribute(hwnd, 36, ctypes.byref(text), 4)     # DWMWA_TEXT_COLOR
    except Exception:
        pass


# compatibilité : ancien nom
dark_titlebar = titlebar


def apply(root, name=None):
    """(Re)pose le thème `name` (clé de PALETTES) sur toute la fenêtre."""
    _set_globals(name or NAME)
    accent_hover = hexa(_mix(PALETTES[NAME]["ACCENT"], (255, 255, 255), 0.25))
    root.configure(bg=BG_)
    st = ttk.Style(root)
    st.theme_use("clam")
    # par défaut tout est posé sur un « panneau » (onglets, cadres) ; Root.* pour le fond
    st.configure(".", background=PANEL_, foreground=TEXT_, fieldbackground=FIELD_,
                 bordercolor=TRACK_, darkcolor=PANEL_, lightcolor=PANEL_, troughcolor=TRACK_,
                 focuscolor=PANEL_, selectbackground=ACCENT_, selectforeground=ON_ACCENT_,
                 insertcolor=TEXT_, arrowcolor=TEXT_, font=FONT)
    st.configure("TFrame", background=PANEL_)
    st.configure("TLabel", background=PANEL_, foreground=TEXT_)
    st.configure("Root.TFrame", background=BG_)
    st.configure("Root.TLabel", background=BG_)
    st.configure("Header.TFrame", background=PANEL_)
    st.configure("Header.TLabel", background=PANEL_, font=("Segoe UI", 13, "bold"))
    st.configure("Muted.TLabel", foreground=MUTED_)
    st.configure("RootMuted.TLabel", background=BG_, foreground=MUTED_)
    st.configure("Section.TLabel", foreground=ACCENT_, font=("Segoe UI", 10, "bold"))
    st.configure("RootSection.TLabel", background=BG_, foreground=ACCENT_,
                 font=("Segoe UI", 10, "bold"))

    st.configure("TNotebook", background=BG_, borderwidth=0, tabmargins=(0, 4, 0, 0))
    st.configure("TNotebook.Tab", background=BG_, foreground=MUTED_, borderwidth=0,
                 padding=(16, 8), font=("Segoe UI", 10, "bold"), lightcolor=BG_,
                 bordercolor=BG_)
    st.map("TNotebook.Tab", background=[("selected", PANEL_), ("active", HOVER_)],
           foreground=[("selected", ACCENT_), ("active", TEXT_)],
           lightcolor=[("selected", ACCENT_)], expand=[("selected", (0, 2, 0, 0))])

    st.configure("TButton", background=TRACK_, foreground=TEXT_, borderwidth=0,
                 padding=(14, 6), relief="flat", lightcolor=TRACK_, darkcolor=TRACK_)
    st.map("TButton", background=[("pressed", ACCENT_), ("active", HOVER_)],
           foreground=[("pressed", ON_ACCENT_)], lightcolor=[("active", HOVER_)],
           darkcolor=[("active", HOVER_)])
    st.configure("Accent.TButton", background=ACCENT_, foreground=ON_ACCENT_,
                 font=("Segoe UI", 10, "bold"), lightcolor=ACCENT_, darkcolor=ACCENT_)
    st.map("Accent.TButton", background=[("pressed", TEXT_), ("active", accent_hover)],
           lightcolor=[("active", accent_hover)], darkcolor=[("active", accent_hover)])

    for w in ("TCheckbutton", "TRadiobutton"):
        st.configure(w, background=PANEL_, foreground=TEXT_, indicatorbackground=FIELD_,
                     indicatorforeground=ON_ACCENT_, indicatormargin=(0, 0, 8, 0), padding=3,
                     upperbordercolor=TRACK_, lowerbordercolor=TRACK_)
        st.map(w, indicatorbackground=[("selected", ACCENT_), ("active", HOVER_)],
               background=[("active", PANEL_)], foreground=[("active", ACCENT_)])

    card_border = hexa(_mix(PALETTES[NAME]["PANEL"], PALETTES[NAME]["TRACK"], 0.7))
    st.configure("TLabelframe", background=PANEL_, bordercolor=card_border, relief="solid",
                 borderwidth=1, lightcolor=card_border, darkcolor=card_border)
    st.configure("TLabelframe.Label", background=PANEL_, foreground=ACCENT_,
                 font=("Segoe UI", 10, "bold"))

    # interrupteurs à la place des cases à cocher (toutes les Checkbutton de l'utilitaire)
    off, on, off_hover = _switch_images(root)
    _switch_n[0] += 1
    elem = f"Switch{_switch_n[0]}.indicator"
    st.element_create(elem, "image", off, ("selected", on), ("active", "!selected", off_hover),
                      border=0, sticky="")
    st.layout("TCheckbutton", [("Checkbutton.padding", {"sticky": "nswe", "children": [
        (elem, {"side": "left", "sticky": ""}),
        ("Checkbutton.focus", {"side": "left", "sticky": "w", "children": [
            ("Checkbutton.label", {"sticky": "nswe"})]})]})])
    st.configure("TCheckbutton", padding=(0, 3, 0, 3), indicatormargin=0)
    st.map("TCheckbutton", foreground=[("active", TEXT_)])

    # barre latérale de navigation, titres de page, lignes de réglage
    st.configure("Side.TFrame", background=BG_)
    st.configure("Nav.TButton", background=BG_, foreground=MUTED_, anchor="w",
                 padding=(14, 9), font=("Segoe UI", 10), borderwidth=0, lightcolor=BG_,
                 darkcolor=BG_, focuscolor=BG_)
    st.map("Nav.TButton", background=[("active", HOVER_)], foreground=[("active", TEXT_)],
           lightcolor=[("active", HOVER_)], darkcolor=[("active", HOVER_)])
    st.configure("NavSel.TButton", background=PANEL_, foreground=ACCENT_, anchor="w",
                 padding=(14, 9), font=("Segoe UI", 10, "bold"), borderwidth=0,
                 lightcolor=PANEL_, darkcolor=PANEL_, focuscolor=PANEL_)
    st.map("NavSel.TButton", background=[("active", PANEL_)])
    st.configure("PageTitle.TLabel", background=PANEL_, foreground=TEXT_,
                 font=("Segoe UI", 16, "bold"))
    st.configure("PageHint.TLabel", background=PANEL_, foreground=MUTED_, font=("Segoe UI", 10))
    st.configure("RowHint.TLabel", background=PANEL_, foreground=MUTED_, font=("Segoe UI", 9))
    st.configure("Dirty.TLabel", background=BG_, foreground=hexa((255, 190, 60)),
                 font=("Segoe UI", 9, "bold"))

    for w in ("TEntry", "TSpinbox", "TCombobox"):
        st.configure(w, fieldbackground=FIELD_, foreground=TEXT_, bordercolor=TRACK_,
                     lightcolor=FIELD_, darkcolor=FIELD_, padding=5, arrowsize=12,
                     background=TRACK_)
        st.map(w, bordercolor=[("focus", ACCENT_)], lightcolor=[("focus", ACCENT_)])
    st.map("TCombobox", fieldbackground=[("readonly", FIELD_)],
           selectbackground=[("readonly", FIELD_)], selectforeground=[("readonly", TEXT_)],
           background=[("active", HOVER_)])
    root.option_add("*TCombobox*Listbox.background", FIELD_)
    root.option_add("*TCombobox*Listbox.foreground", TEXT_)
    root.option_add("*TCombobox*Listbox.selectBackground", ACCENT_)
    root.option_add("*TCombobox*Listbox.selectForeground", ON_ACCENT_)
    root.option_add("*TCombobox*Listbox.font", FONT)
    root.option_add("*TCombobox*Listbox.borderWidth", 0)

    st.configure("Horizontal.TScale", background=ACCENT_, troughcolor=TRACK_, borderwidth=0,
                 lightcolor=ACCENT_, darkcolor=ACCENT_, sliderthickness=14)
    st.configure("Treeview", background=FIELD_, fieldbackground=FIELD_, foreground=TEXT_,
                 rowheight=26, borderwidth=0)
    st.map("Treeview", background=[("selected", ACCENT_)],
           foreground=[("selected", ON_ACCENT_)])
    st.configure("Treeview.Heading", background=TRACK_, foreground=MUTED_, borderwidth=0,
                 relief="flat", font=("Segoe UI", 9, "bold"))
    st.map("Treeview.Heading", background=[("active", HOVER_)])
    st.configure("Vertical.TScrollbar", background=TRACK_, troughcolor=PANEL_, borderwidth=0,
                 arrowcolor=MUTED_, lightcolor=TRACK_, darkcolor=TRACK_)
    st.map("Vertical.TScrollbar", background=[("active", ACCENT_)])

    alive = []
    for widget, opts in _painted:
        try:
            widget.configure(**{o: color(k) for o, k in opts.items()})
            alive.append((widget, opts))
        except tk.TclError:
            pass                       # widget détruit
        if isinstance(widget, HeaderBar):
            widget.redraw()
    _painted[:] = alive
    titlebar(root)
