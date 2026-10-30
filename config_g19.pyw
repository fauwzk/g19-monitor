"""Utilitaire de configuration du moniteur G19 (double-clic pour l'ouvrir).

Les réglages enregistrés sont appliqués à chaud par l'appli, sans la relancer.
"""
import os
import subprocess
import sys
import threading
import time
import tkinter as tk
import urllib.error
import webbrowser
from datetime import datetime
from pathlib import Path
from tkinter import colorchooser, filedialog, messagebox, ttk
from tkinter import font as tkfont

APP_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(APP_DIR))
os.chdir(APP_DIR)

from PIL import Image, ImageTk  # noqa: E402

import install_hooks  # noqa: E402
import install_startup  # noqa: E402
from g19 import afterburner, backup, config, instance, night, remote, rtss, screen, settings, steam_live, theme, version, volume, fuel  # noqa: E402
from g19 import discord as discord_rpc  # noqa: E402
from g19.alerts import DEFAULT_THRESHOLDS, RULES  # noqa: E402
from g19.launcher import launch  # noqa: E402
from g19.fans import LABELS as FAN_LABELS  # noqa: E402
from g19.weather import geocode  # noqa: E402
from g19.claude_status import read_sessions  # noqa: E402
from g19.render import THEME_LABELS, render, theme_of  # noqa: E402
from g19.tray import make_icon  # noqa: E402

TITLES = settings.PAGE_TITLES
BY_TITLE = {v: k for k, v in TITLES.items()}
GAME_PAGES = {"": "Ne rien changer", "gpu": "GPU", "games": "Jeux"}
PREVIEW_SCALE = 1.4
LIVE = "● G19 en direct"
# case du rétroéclairage → réglage de sa couleur
COLOR_OF = {"backlight_alerts": "color_alert", "backlight_waiting": "color_waiting",
            "backlight_working": "color_working", "backlight_done": "color_done",
            "backlight_discord": "color_discord", "backlight_notifs": "color_notif",
            "notif_whatsapp": "color_whatsapp", "notif_snap": "color_snap"}
NIGHT_THEMES = {"": "inchangé", "dark": "Sombre", "g19": "G19", "light": "Clair",
                "g15": "Rétro G15", "neon": "Néon", "dynamic": "Dynamique",
                "red": "Rouge nuit", "contrast": "Haut contraste", "glacier": "Glacier",
                "braise": "Braise", "terminal": "Terminal", "hud": "HUD cockpit",
                "analog": "Cadrans", "paper": "Papier", "paper_dark": "Papier sombre"}   # aperçu = l'écran réellement affiché par l'appli, piloté au pavé
# touches du clavier de l'ordinateur → touches du G19 (quand l'aperçu a le focus)
KEY_BINDINGS = {"<Left>": "left", "<Right>": "right", "<Up>": "up", "<Down>": "down",
                "<Return>": "ok", "<space>": "ok", "<Escape>": "cancel", "<BackSpace>": "cancel",
                "m": "menu"}
TAB_WIDTH = 460           # largeur de départ ; ajustée au contenu le plus large
PORTAL = "https://discord.com/developers/applications"


# page → (icône Segoe Fluent / MDL2, phrase d'explication sous le titre)
PAGE_INFO = {
    "Écrans": ("\uE8A9", "Les pages affichées sur le G19, leur ordre et celle du démarrage."),
    "Affichage": ("\uE7F4", "Thème, fluidité et réglages de l'écran du G19."),
    "Écran du G19": ("\uE706", "Luminosité, contraste et netteté de l'écran, avec une mire "
                                "pour les régler à l'œil."),
    "Bandeaux": ("\uE8BD", "Les messages qui glissent en bas de l'écran, sur toutes les pages."),
    "Mode nuit": ("\uE708", "Écran assombri et clavier discret pendant la nuit."),
    "Météo et réseau": ("\uE909", "Ville de la météo et cible du ping de l'écran Réseau."),
    "Alertes et clavier": ("\uE7BA", "Seuils d'alerte et rétroéclairage du clavier comme voyant."),
    "Raccourcis": ("\uE71B", "Les applis à ouvrir depuis le menu du G19."),
    "Audio": ("\uE7F5", "Profils audio : casque, haut-parleurs\u2026 \u00E0 changer d'un geste."),
    "Carburant": ("\uE804", "Prix des stations suivies dans Home Assistant."),
    "Discord": ("\uE716", "Connexion à Discord : salon vocal, messages, appels."),
    "Steam": ("\uE7FC", "Téléchargements et amis en ligne."),
    "Système": ("\uE713", "L'appli, le démarrage, les ventilateurs et la sauvegarde."),
}


def icon_font():
    families = set(tkfont.families())
    for name in ("Segoe Fluent Icons", "Segoe MDL2 Assets"):
        if name in families:
            return (name, 12)
    return None


FUEL_AUTO = "automatique"
FUEL_MAIN = {"": FUEL_AUTO, **{f: f for f in ("Gazole", "E10", "SP95", "SP98", "E85", "GPLc")}}
AUDIO_KEEP = "inchangé"
AUDIO_KEEP_IN = "micro inchangé"


class Sidebar(ttk.Frame):
    """Navigation verticale (icône + nom) ; les pages sont empilées dans `content`."""

    def __init__(self, master, content):
        super().__init__(master, style="Side.TFrame", padding=(0, 4, 0, 4))
        self.content = content
        self.pages, self.items = [], []
        self.current = 0
        self._icon_font = icon_font()

    def add(self, page, text):
        icon, _hint = PAGE_INFO.get(text, ("", ""))
        item = tk.Frame(self, cursor="hand2")
        bar = tk.Frame(item, width=3)
        bar.pack(side="left", fill="y")
        if self._icon_font and icon:
            ic = tk.Label(item, text=icon, font=self._icon_font, width=2)
            ic.pack(side="left", padx=(10, 4), pady=7)
        else:
            ic = tk.Label(item, text="", width=1)
            ic.pack(side="left", padx=(6, 0))
        lb = tk.Label(item, text=text, font=("Segoe UI", 10), anchor="w")
        lb.pack(side="left", fill="x", expand=True, padx=(4, 16), pady=7)
        item.pack(fill="x", pady=1)
        i = len(self.pages)
        for w in (item, ic, lb):
            w.bind("<Button-1>", lambda e, i=i: self.select(i))
            w.bind("<Enter>", lambda e, i=i: self._hover(i, True))
            w.bind("<Leave>", lambda e, i=i: self._hover(i, False))
        self.pages.append(page)
        self.items.append((item, bar, ic, lb))
        page.grid(row=0, column=0, sticky="nsew", in_=self.content)
        self.select(self.current if len(self.pages) > 1 else 0)

    def tabs(self):
        return self.pages

    def select(self, i):
        self.current = i
        self.pages[i].tkraise()
        self.refresh()

    def _hover(self, i, inside):
        if i != self.current:
            item, bar, ic, lb = self.items[i]
            bg = theme.HOVER_ if inside else theme.BG_
            for w in (item, bar, ic, lb):
                w.configure(bg=bg)

    def refresh(self):
        """Couleurs selon le thème et la page choisie (appelé aussi après un changement de thème)."""
        for k, (item, bar, ic, lb) in enumerate(self.items):
            sel = k == self.current
            bg = theme.PANEL_ if sel else theme.BG_
            for w in (item, ic, lb):
                w.configure(bg=bg)
            bar.configure(bg=theme.ACCENT_ if sel else bg)
            ic.configure(fg=theme.ACCENT_ if sel else theme.MUTED_)
            lb.configure(fg=theme.TEXT_ if sel else theme.MUTED_,
                         font=("Segoe UI", 10, "bold" if sel else "normal"))


class ConfigApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("G19 Monitor — Configuration")
        self.resizable(False, False)
        self.s = settings.load()
        theme.apply(self, theme_of(self.s))   # l'utilitaire prend le thème de l'écran du G19
        self._icon = ImageTk.PhotoImage(make_icon())
        self.iconphoto(True, self._icon)
        self.ctx = None
        self.media = None
        self._photo = None
        self._last_sample = 0.0
        self._tabs = []

        # bandeau façon G19 : titre à gauche, état de l'appli à droite
        self.header = theme.HeaderBar(self, "G19 Monitor", f"configuration · {version.label()}")
        self.header.pack(fill="x")
        theme.paint(self.header, bg="BG")

        # version et mises à jour, visibles sur toutes les pages
        bar = ttk.Frame(self, padding=(14, 6, 12, 0), style="Root.TFrame")
        bar.pack(fill="x")
        ttk.Label(bar, text=f"Version {version.label()}", style="Muted.TLabel").pack(side="left")
        self.update_label = ttk.Label(bar, text="", style="Muted.TLabel")
        self.update_label.pack(side="left", padx=(12, 0))
        ttk.Button(bar, text="Vérifier les mises à jour", command=self._check_update).pack(
            side="right")

        body = ttk.Frame(self, padding=(0, 12, 12, 12), style="Root.TFrame")
        body.pack(fill="both", expand=True)
        main = ttk.Frame(body, style="Root.TFrame")
        main.grid(row=0, column=0, sticky="nsew")
        content = ttk.Frame(main, style="Root.TFrame")
        nb = self.nav = Sidebar(main, content)
        nb.pack(side="left", fill="y")
        content.pack(side="left", fill="both", expand=True)
        self._tab_pages(nb)
        self._tab_display(nb)
        self._tab_screen(nb)
        self._tab_toasts(nb)
        self._tab_night(nb)
        self._tab_weather(nb)
        self._tab_alerts(nb)
        self._tab_shortcuts(nb)
        self._tab_audio(nb)
        self._tab_fuel(nb)
        self._tab_discord(nb)
        self._tab_steam(nb)
        self._tab_system(nb)

        right = ttk.Frame(body, padding=(16, 0, 0, 0), style="Root.TFrame")
        right.grid(row=0, column=1, sticky="n")
        top = ttk.Frame(right, style="Root.TFrame")
        top.pack(fill="x", pady=(4, 6))
        ttk.Label(top, text="APERÇU", style="RootSection.TLabel").pack(side="left")
        self.preview_page = tk.StringVar(value=LIVE if instance.is_running()
                                         else TITLES[self.s["pages"][0]])
        ttk.Combobox(top, textvariable=self.preview_page, values=[LIVE, *TITLES.values()],
                     state="readonly", width=16).pack(side="right")
        w, h = int(320 * PREVIEW_SCALE), int(240 * PREVIEW_SCALE)
        frame = theme.paint(tk.Frame(right, padx=2, pady=2), bg="ACCENT")  # liseré façon écran
        frame.pack()
        # image vide de la bonne taille : sans image, width/height d'un Label sont en caractères
        self._blank = tk.PhotoImage(width=w, height=h)
        self.preview = tk.Label(frame, image=self._blank, text="chargement…", compound="center",
                                bd=0)
        theme.paint(self.preview, bg="BG", fg="MUTED")
        self.preview.pack()
        self.preview.config(takefocus=1)
        self.preview.bind("<Button-1>", lambda e: self.preview.focus_set())
        for seq, button in KEY_BINDINGS.items():
            self.preview.bind(seq, lambda e, b=button: self._press(b))
        self._keypad(right)
        self._last_mirror_req = 0.0

        bottom = ttk.Frame(body, padding=(12, 12, 0, 0), style="Root.TFrame")
        bottom.grid(row=1, column=0, columnspan=2, sticky="ew")
        self.status = ttk.Label(bottom, text="", style="RootMuted.TLabel")
        self.status.pack(side="left")
        self.dirty_label = ttk.Label(bottom, text="", style="Dirty.TLabel")
        ttk.Button(bottom, text="Fermer", command=self.close).pack(side="right")
        self.protocol("WM_DELETE_WINDOW", self.close)
        ttk.Button(bottom, text="Enregistrer", style="Accent.TButton",
                   command=self.save).pack(side="right", padx=8)
        self.dirty_label.pack(side="right", padx=8)

        # réglages tels qu'affichés : seuls ceux modifiés ici sont enregistrés, et ceux changés
        # ailleurs (menu du G19) sont repris dans la fenêtre
        self._base = self.collect()
        self._watch = settings.Watcher()
        threading.Thread(target=self._load_ctx, daemon=True).start()
        self._fit_tabs()
        self._center()
        self.after(300, self._tick)

    def _center(self):
        """Fenêtre centrée sur l'écran (et jamais plus grande que lui)."""
        self.update_idletasks()
        w, h = self.winfo_reqwidth(), self.winfo_reqheight()
        sw, sh = self.winfo_screenwidth(), self.winfo_screenheight()
        self.geometry(f"+{max(0, (sw - w) // 2)}+{max(0, (sh - h) // 2 - 20)}")

    def _tab(self, nb, text):
        """Onglet à contenu défilant ; sa taille est ajustée par _fit_tabs une fois tout construit."""
        outer = ttk.Frame(nb.content)
        head = ttk.Frame(outer, padding=(22, 16, 22, 4))
        head.pack(fill="x")
        ttk.Label(head, text=text, style="PageTitle.TLabel").pack(anchor="w")
        hint = PAGE_INFO.get(text, ("", ""))[1]
        if hint:
            ttk.Label(head, text=hint, style="PageHint.TLabel").pack(anchor="w", pady=(2, 0))
        nb.add(outer, text=text)
        canvas = theme.paint(tk.Canvas(outer, highlightthickness=0, width=TAB_WIDTH,
                                       height=400), bg="PANEL")
        bar = ttk.Scrollbar(outer, orient="vertical", command=canvas.yview)
        inner = ttk.Frame(canvas, padding=(22, 8, 22, 16))
        win = canvas.create_window(0, 0, window=inner, anchor="nw")
        # le contenu prend toute la largeur de la page (cartes étirées, contrôles à droite)
        canvas.bind("<Configure>", lambda e: canvas.itemconfigure(win, width=e.width), add="+")
        canvas.configure(yscrollcommand=bar.set)
        canvas.pack(side="left", fill="both", expand=True)

        def resized(_event=None):
            canvas.configure(scrollregion=(0, 0, inner.winfo_reqwidth(), inner.winfo_reqheight()))
            if inner.winfo_reqheight() > int(canvas["height"]):
                bar.pack(side="right", fill="y")
            else:
                bar.pack_forget()

        def wheel(event):
            if inner.winfo_reqheight() > int(canvas["height"]):
                canvas.yview_scroll(-event.delta // 120, "units")

        inner.bind("<Configure>", resized)
        canvas.bind("<Enter>", lambda e: canvas.bind_all("<MouseWheel>", wheel))
        canvas.bind("<Leave>", lambda e: canvas.unbind_all("<MouseWheel>"))
        self._tabs.append((canvas, inner, resized))
        return inner

    def _fit_tabs(self):
        """Tous les onglets à la taille du plus grand contenu, sans dépasser l'écran (ceux qui
        restent trop hauts défilent)."""
        self.update_idletasks()
        width = max(inner.winfo_reqwidth() for _, inner, _ in self._tabs)
        tallest = max(inner.winfo_reqheight() for _, inner, _ in self._tabs)
        room = self.winfo_screenheight() - 320   # bandeau, titre, boutons, barre des tâches
        height = max(int(240 * PREVIEW_SCALE) + 40, min(tallest, room))
        for canvas, _inner, resized in self._tabs:
            canvas.configure(width=width, height=height)
            resized()

    # --- onglets ---

    def _tab_pages(self, nb):
        f = self._tab(nb, "Écrans")
        ttk.Label(f, text="Pages affichées (double-clic pour activer/désactiver) :").grid(
            row=0, column=0, columnspan=2, sticky="w")
        self.tree = ttk.Treeview(f, columns=("on",), show="tree headings", height=8,
                                 selectmode="browse")
        self.tree.heading("#0", text="Page")
        self.tree.heading("on", text="Affichée")
        self.tree.column("#0", width=150)
        self.tree.column("on", width=70, anchor="center")
        self.tree.grid(row=1, column=0, sticky="nsew", pady=4)
        enabled = self.s["pages"]
        for pid in enabled + [p for p in TITLES if p not in enabled]:
            self.tree.insert("", "end", iid=pid, text=TITLES[pid],
                             values=("✔" if pid in enabled else "",))
        self.tree.bind("<Double-1>", lambda e: self._toggle_page())
        self.tree.bind("<<TreeviewSelect>>", self._on_select)

        btns = ttk.Frame(f)
        btns.grid(row=1, column=1, sticky="n", padx=(8, 0), pady=4)
        ttk.Button(btns, text="▲ Monter", command=lambda: self._move(-1)).pack(fill="x")
        ttk.Button(btns, text="▼ Descendre", command=lambda: self._move(1)).pack(fill="x", pady=4)
        ttk.Button(btns, text="Afficher / masquer", command=self._toggle_page).pack(fill="x")

        box = ttk.LabelFrame(f, text="Au démarrage", padding=8)
        box.grid(row=2, column=0, columnspan=2, sticky="ew", pady=(10, 0))
        self.remember = tk.BooleanVar(value=self.s["remember_page"])
        ttk.Radiobutton(box, text="Rouvrir sur la dernière page affichée", variable=self.remember,
                        value=True).grid(row=0, column=0, columnspan=2, sticky="w")
        ttk.Radiobutton(box, text="Toujours ouvrir sur :", variable=self.remember,
                        value=False).grid(row=1, column=0, sticky="w")
        self.start_page = tk.StringVar(value=TITLES.get(self.s["start_page"], "Système"))
        ttk.Combobox(box, textvariable=self.start_page, values=list(TITLES.values()),
                     state="readonly", width=12).grid(row=1, column=1, sticky="w", padx=6)

        box = ttk.LabelFrame(f, text="Au lancement d'un jeu", padding=8)
        box.grid(row=3, column=0, columnspan=2, sticky="ew", pady=(10, 0))
        ttk.Label(box, text="Afficher la page :").grid(row=0, column=0, sticky="w")
        self.game_page = tk.StringVar(value=GAME_PAGES.get(self.s["game_page"], "GPU"))
        ttk.Combobox(box, textvariable=self.game_page, values=list(GAME_PAGES.values()),
                     state="readonly", width=16).grid(row=0, column=1, sticky="w", padx=6)

    # --- briques de mise en page : cartes et lignes de réglage ---

    def _card(self, page, title=None):
        card = ttk.LabelFrame(page, text=title, padding=(14, 8, 14, 10)) if title else \
            ttk.Frame(page)
        card.pack(fill="x", pady=(0, 12))
        card.columnconfigure(0, weight=1)
        card.next_row = 0
        return card

    def _row(self, card, label, make, hint=None):
        """Libellé à gauche, contrôle à droite, aide en petit dessous."""
        r = card.next_row
        ttk.Label(card, text=label).grid(row=r, column=0, sticky="w", pady=(6, 0))
        widget = make(card)
        widget.grid(row=r, column=1, sticky="e", padx=(16, 0), pady=(6, 0))
        if hint:
            ttk.Label(card, text=hint, style="RowHint.TLabel", wraplength=320,
                      justify="left").grid(row=r + 1, column=0, columnspan=2, sticky="w")
        card.next_row += 2
        return widget

    def _switch(self, card, label, var, hint=None):
        return self._row(card, label, lambda m: ttk.Checkbutton(m, variable=var), hint)

    def _spin(self, var, lo, hi, step=1, width=6):
        return lambda m: ttk.Spinbox(m, from_=lo, to=hi, increment=step, width=width,
                                     textvariable=var)

    def _tab_display(self, nb):
        f = self._tab(nb, "Affichage")
        self.fps = tk.IntVar(value=self.s["fps"])
        self.power = tk.IntVar(value=self.s["gpu_power_max"])
        self.strip_s = tk.IntVar(value=self.s["claude_strip_seconds"])
        self.theme = tk.StringVar(value=THEME_LABELS[theme_of(self.s)])
        self.wallpaper_bg = tk.BooleanVar(value=self.s["wallpaper_bg"])
        self.wallpaper_dim = tk.IntVar(value=self.s["wallpaper_dim"])

        card = self._card(f, "Apparence")

        def theme_box(m):
            box = ttk.Combobox(m, textvariable=self.theme, values=list(THEME_LABELS.values()),
                               state="readonly", width=20)
            # l'utilitaire change de thème avec l'écran (aperçu immédiat)
            box.bind("<<ComboboxSelected>>", lambda e: self._restyle(
                {v: k for k, v in THEME_LABELS.items()}.get(self.theme.get(), "dark")))
            return box

        self._row(card, "Thème", theme_box, "Celui de l'écran du G19 ; cette fenêtre le suit.")
        self._switch(card, "Fond d'écran Windows derrière les pages", self.wallpaper_bg,
                     "Flouté, avec des panneaux translucides ; suit les changements de fond "
                     "d'écran (diaporama compris). Toujours actif avec le thème Aero.")
        self._row(card, "Assombrissement du fond (%)", self._spin(self.wallpaper_dim, 0, 90, 5),
                  "Plus haut = texte plus lisible, fond d'écran plus discret.")
        self._row(card, "Images par seconde", self._spin(self.fps, 2, 60),
                  "Jusqu'à 60. Une page fixe ne coûte presque rien (images identiques non "
                  "renvoyées) ; la fluidité réelle s'affiche dans le menu du G19.")

        card = self._card(f, "Pages")
        self._row(card, "Puissance max. du GPU (W)", self._spin(self.power, 100, 700, 5),
                  "Échelle de la jauge Puissance de l'écran GPU.")
        self._row(card, "Encart Claude masqué après (s)", self._spin(self.strip_s, 0, 600, 5),
                  "Après la fin du dernier agent, l'encart s'efface et le voyant passe au gris "
                  "(0 = jamais).")

    def _slider(self, var, lo, hi, step, unit="%"):
        """Curseur avec sa valeur à droite."""
        def make(m):
            frame = ttk.Frame(m)
            value = ttk.Label(frame, width=6, anchor="e")

            def moved(v):
                n = int(round(float(v) / step) * step)
                var.set(n)
                value.config(text=f"{n} {unit}")

            ttk.Scale(frame, from_=lo, to=hi, orient="horizontal", length=180, variable=var,
                      command=moved).pack(side="left")
            value.pack(side="left", padx=(8, 0))
            value.config(text=f"{var.get()} {unit}")
            var.trace_add("write", lambda *_: value.config(text=f"{var.get()} {unit}"))
            return frame
        return make

    def _tab_screen(self, nb):
        f = self._tab(nb, "Écran du G19")
        self.scr_brightness = tk.IntVar(value=self.s["screen_brightness"])
        self.scr_contrast = tk.IntVar(value=self.s["screen_contrast"])
        self.scr_gamma = tk.IntVar(value=self.s["screen_gamma"])
        self.scr_saturation = tk.IntVar(value=self.s["screen_saturation"])
        self.scr_sharpen = tk.BooleanVar(value=self.s["screen_sharpen"])

        card = self._card(f, "Image")
        self._row(card, "Luminosité", self._slider(self.scr_brightness, 50, 150, 5))
        self._row(card, "Contraste", self._slider(self.scr_contrast, 50, 150, 5))
        self._row(card, "Tons sombres (gamma)", self._slider(self.scr_gamma, 60, 160, 5),
                  "Au-dessus de 100 %, les gris foncés et les textes estompés ressortent : "
                  "l'écran du G19 a tendance à les écraser.")
        self._row(card, "Saturation", self._slider(self.scr_saturation, 0, 200, 10),
                  "0 % : noir et blanc.")
        self._switch(card, "Netteté renforcée", self.scr_sharpen,
                     "Contours des petits textes plus nets.")

        card = self._card(f, "Réglage à l'œil")

        def buttons(m):
            line = ttk.Frame(m)
            ttk.Button(line, text="Afficher la mire sur le G19", style="Accent.TButton",
                       command=self._show_pattern).pack(side="left")
            ttk.Button(line, text="Valeurs d'origine",
                       command=self._reset_screen).pack(side="left", padx=(6, 0))
            return line

        self._row(card, "Mire de réglage", buttons,
                  "Marches de gris, couleurs et textes de 8 à 16 px pendant 20 s. Enregistre "
                  "pour voir l'effet de tes réglages sur la mire.")

    def _show_pattern(self):
        if not instance.is_running():
            self._flash("L'appli doit tourner pour afficher la mire.")
            return
        config.save("flash_test.json", {"kind": "pattern", "at": time.time()})
        self._flash("Mire affichée sur le G19 pendant 20 s (une touche pour la fermer).")

    def _reset_screen(self):
        for var, v in ((self.scr_brightness, 100), (self.scr_contrast, 100),
                       (self.scr_gamma, 100), (self.scr_saturation, 100)):
            var.set(v)
        self.scr_sharpen.set(False)

    def _tab_toasts(self, nb):
        f = self._tab(nb, "Bandeaux")
        self.toasts = tk.BooleanVar(value=self.s["discord_toasts"])
        self.toast_s = tk.IntVar(value=self.s["toast_seconds"])
        self.win_toasts = tk.BooleanVar(value=self.s["win_toasts"])
        self.notif_ignore = tk.StringVar(value=", ".join(self.s["notif_ignore"]))
        self.media_toasts = tk.BooleanVar(value=self.s["media_toasts"])
        self.device_toasts = tk.BooleanVar(value=self.s["device_toasts"])
        self.steam_toasts = tk.BooleanVar(value=self.s["steam_toasts"])
        self.voice_toasts = tk.BooleanVar(value=self.s["voice_toasts"])
        self.stream_toasts = tk.BooleanVar(value=self.s["stream_toasts"])
        self.docker_toasts = tk.BooleanVar(value=self.s["docker_toasts"])
        self.fuel_toasts = tk.BooleanVar(value=self.s["fuel_toasts"])
        self.page_toasts = tk.BooleanVar(value=self.s["page_toasts"])
        self.driver_toasts = tk.BooleanVar(value=self.s["driver_toasts"])
        self.idle_screen = tk.BooleanVar(value=self.s["idle_screen"])
        self.idle_minutes = tk.IntVar(value=self.s["idle_minutes"])
        self.away_summary = tk.BooleanVar(value=self.s["away_summary"])
        self.away_min = tk.IntVar(value=self.s["away_min_minutes"])

        card = self._card(f, "Messages")
        self._switch(card, "Messages Discord", self.toasts)
        self._switch(card, "Notifications Windows", self.win_toasts)
        self._row(card, "Applis ignorées", lambda m: ttk.Entry(m, textvariable=self.notif_ignore,
                                                               width=26),
                  "Séparées par des virgules (ex. : Sécurité Windows, PowerToys). Les notifs "
                  "Discord sont masquées d'office quand l'écran Discord est connecté.")
        self._row(card, "Durée d'affichage (s)", self._spin(self.toast_s, 2, 30))

        card = self._card(f, "Événements")
        self._switch(card, "Changement de musique / média", self.media_toasts)
        self._switch(card, "Périphérique connecté ou retiré", self.device_toasts,
                     "USB, Bluetooth et audio, avec la batterie quand l'appareil en a une.")
        self._switch(card, "Ami Steam connecté", self.steam_toasts, "Avec sa photo de profil.")
        self._switch(card, "Arrivée / départ dans l'appel Discord", self.voice_toasts,
                     "Quand quelqu'un rejoint ou quitte le salon vocal où tu es.")
        self._switch(card, "Connexion en streaming à ce PC", self.stream_toasts,
                     "Moonlight (via Sunshine) ou Parsec, avec un voyant rouge dans la barre du "
                     "haut tant que la session dure.")
        self._switch(card, "Conteneur Docker en panne", self.docker_toasts,
                     "Arrêté en erreur, ou qui redémarre en boucle (3 fois en 5 min).")
        self._switch(card, "Carburant en rupture ou de retour", self.fuel_toasts,
                     "Une station suivie dans Home Assistant (Prix Carburant) n'a plus un "
                     "carburant, ou l'a de nouveau.")
        self._switch(card, "Page de nouveau disponible", self.page_toasts,
                     "Les pages Discord et Docker sont masquées tant que l'appli est fermée ; "
                     "un bandeau prévient quand elles reviennent.")
        self._switch(card, "Nouveau pilote graphique AMD", self.driver_toasts,
                     "D'après le catalogue que tient AMD Software ; rappel une fois par jour "
                     "tant qu'il n'est pas installé.")

        card = self._card(f, "PC au repos")
        self._switch(card, "Horloge quand le PC est verrouillé ou inactif", self.idle_screen,
                     "Avec la météo et ce qui est arrivé entre-temps. Pas pendant un jeu ni "
                     "une vidéo ; une touche du G19 réveille l'écran.")
        self._row(card, "Inactif après (min)", self._spin(self.idle_minutes, 1, 120))
        self._switch(card, "Résumé « pendant ton absence » au retour", self.away_summary,
                     "Messages, amis, agents Claude, téléchargements… une touche pour fermer.")
        self._row(card, "Absence minimale (min)", self._spin(self.away_min, 0, 240))

    def _tab_night(self, nb):
        f = self._tab(nb, "Mode nuit")
        self.night_mode = tk.BooleanVar(value=self.s["night_mode"])
        self.night_start = tk.StringVar(value=self.s["night_start"])
        self.night_end = tk.StringVar(value=self.s["night_end"])
        self.night_dim = tk.IntVar(value=self.s["night_dim"])
        self.night_theme = tk.StringVar(value=NIGHT_THEMES.get(self.s["night_theme"], "inchangé"))
        self.night_quiet = tk.BooleanVar(value=self.s["night_quiet"])

        card = self._card(f, "Mode nuit")
        self._switch(card, "Activer", self.night_mode)

        def hours(m):
            line = ttk.Frame(m)
            ttk.Combobox(line, textvariable=self.night_start, values=night.HOURS, width=6,
                         state="readonly").pack(side="left")
            ttk.Label(line, text="→").pack(side="left", padx=6)
            ttk.Combobox(line, textvariable=self.night_end, values=night.HOURS, width=6,
                         state="readonly").pack(side="left")
            return line

        self._row(card, "Plage horaire", hours)
        card = self._card(f, "Pendant la nuit")
        self._row(card, "Luminosité de l'écran (%)", self._spin(self.night_dim, 10, 100, 10))
        self._row(card, "Thème", lambda m: ttk.Combobox(
            m, textvariable=self.night_theme, values=list(NIGHT_THEMES.values()), width=14,
            state="readonly"), "« inchangé » garde le thème du jour.")
        self._switch(card, "Clavier discret", self.night_quiet,
                     "Seules les alertes font clignoter le clavier.")

    def _tab_weather(self, nb):
        f = self._tab(nb, "Météo et réseau")
        self.city = tk.StringVar(value=self.s["weather_city"])
        self.ping_target = tk.StringVar(value=self.s["ping_target"])

        card = self._card(f, "Météo")

        def city(m):
            line = ttk.Frame(m)
            ttk.Entry(line, textvariable=self.city, width=20).pack(side="left")
            ttk.Button(line, text="Vérifier", command=self._check_city).pack(side="left",
                                                                            padx=(6, 0))
            return line

        self._row(card, "Ville", city, "Vide : position d'après l'adresse IP.")
        self.city_state = ttk.Label(card, text="", style="RowHint.TLabel")
        self.city_state.grid(row=card.next_row, column=0, columnspan=2, sticky="w")
        card.next_row += 1

        card = self._card(f, "Réseau")
        self._row(card, "Cible du ping", lambda m: ttk.Entry(m, textvariable=self.ping_target,
                                                             width=22),
                  "Un ping par seconde pour l'écran Réseau (1.1.1.1 par défaut) ; alertes en "
                  "jeu sur un pic de latence ou des pertes.")

    def _check_city(self):
        city = self.city.get().strip()
        if not city:
            return
        self.city_state.config(text="Recherche…")

        def work():
            try:
                p = geocode(city)
                msg = f"✔ {p['name']}, {p['admin']}, {p['country']}" if p else "✘ ville introuvable"
            except Exception:
                msg = "✘ pas de connexion"
            self.after(0, lambda: self.city_state.config(text=msg))

        threading.Thread(target=work, daemon=True).start()

    def _tab_alerts(self, nb):
        f = self._tab(nb, "Alertes et clavier")
        self.alerts_on = tk.BooleanVar(value=self.s["alerts_on"])
        ttk.Checkbutton(f, text="Alertes actives (bandeau, cadre rouge, rétroéclairage)",
                        variable=self.alerts_on).grid(row=0, column=0, columnspan=2, sticky="w")
        box = ttk.LabelFrame(f, text="Seuils (0 = désactivé)", padding=8)
        box.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(10, 0))
        thresholds = {**DEFAULT_THRESHOLDS, **self.s["alerts"]}
        self.thresholds = {}
        for i, (key, (label, unit)) in enumerate(RULES.items()):
            var = tk.IntVar(value=thresholds[key])
            self.thresholds[key] = var
            ttk.Label(box, text=label).grid(row=i, column=0, sticky="w", pady=2)
            ttk.Spinbox(box, from_=0, to=120, width=5, textvariable=var).grid(row=i, column=1,
                                                                              padx=8)
            ttk.Label(box, text=unit, style="Muted.TLabel").grid(row=i, column=2, sticky="w")

        box = ttk.LabelFrame(f, text="Rétroéclairage du G19 comme voyant", padding=8)
        box.grid(row=2, column=0, columnspan=2, sticky="ew", pady=(10, 0))
        self.backlight = {}
        opts = [("backlight", "Activer (sinon l'éclairage de LGS n'est jamais modifié)"),
                ("backlight_alerts", "Clignote pendant une alerte"),
                ("backlight_waiting", "Pulse quand Claude attend ta réponse"),
                ("backlight_working", "Couleur fixe quand Claude travaille"),
                ("backlight_done", "Clignote quand Claude a fini"),
                ("backlight_discord", "Clignote à chaque message Discord"),
                ("backlight_notifs", "Clignote à chaque notification Windows"),
                ("notif_whatsapp", "WhatsApp : sa propre couleur"),
                ("notif_snap", "Snapchat : sa propre couleur")]
        self.blinks = {}
        self.colors = {}
        self.color_swatches = {}
        blink_of = {"backlight_done": "blinks_done", "backlight_discord": "blinks_discord",
                    "backlight_notifs": "blinks_notifs"}
        for i, (key, text) in enumerate(opts):
            if key.startswith("notif_"):
                # couleur à part pour une appli : même réglage (et nombre) que les notifs
                ttk.Label(box, text=text, style="Muted.TLabel").grid(row=i, column=0,
                                                                     sticky="w", padx=(40, 0))
                ttk.Button(box, text="Tester", command=lambda k=key: self._test_flash(k)).grid(
                    row=i, column=3, padx=(6, 0))
            else:
                var = tk.BooleanVar(value=self.s[key])
                self.backlight[key] = var
                ttk.Checkbutton(box, text=text, variable=var).grid(
                    row=i, column=0, sticky="w", padx=(0 if i == 0 else 16, 0))
            if key in blink_of:
                n = tk.IntVar(value=self.s[blink_of[key]])
                self.blinks[blink_of[key]] = n
                ttk.Spinbox(box, from_=1, to=10, width=3, textvariable=n).grid(row=i, column=1,
                                                                             padx=(8, 2))
                ttk.Label(box, text="fois", style="Muted.TLabel").grid(row=i, column=2, sticky="w")
                ttk.Button(box, text="Tester", command=lambda k=key: self._test_flash(k)).grid(
                    row=i, column=3, padx=(6, 0))
            elif key == "backlight_waiting":
                ttk.Button(box, text="Tester", command=lambda: self._test_pulse("waiting")).grid(
                    row=i, column=3, padx=(6, 0))
            color_key = COLOR_OF.get(key)
            if color_key:
                # couleur de l'effet : pastille cliquable
                self.colors[color_key] = self.s[color_key]
                sw = tk.Label(box, width=3, bd=1, relief="solid", cursor="hand2",
                              bg=self.s[color_key])
                sw.grid(row=i, column=4, padx=(8, 0))
                self.color_swatches[color_key] = sw
                sw.bind("<Button-1>", lambda e, k=color_key, w=sw: self._pick_color(k, w))
        self.blink_ms = tk.IntVar(value=settings.blink_ms(self.s["blink_ms"]))
        self.pulse_ms = tk.IntVar(value=settings.pulse_ms(self.s["pulse_ms"], 300))
        for k, (label, var, rng) in enumerate((
                ("Vitesse de clignotement", self.blink_ms, settings.BLINK_RANGE),
                ("Pulsation Claude attend", self.pulse_ms, settings.PULSE_RANGE))):
            row = len(opts) + k
            ttk.Label(box, text=label).grid(row=row, column=0, sticky="w", padx=(16, 0),
                                            pady=(6, 0))
            self._pulse_slider(box, var, rng).grid(row=row, column=1, columnspan=4, sticky="w",
                                                   padx=(8, 0), pady=(6, 0))
        self.base_color = self.s["backlight_base"]
        r = len(opts) + 2
        ttk.Label(box, text="Couleur au repos (après un effet)").grid(row=r, column=0, sticky="w",
                                                                  padx=(16, 0), pady=(6, 0))
        sw = ttk.Frame(box)
        sw.grid(row=r, column=1, columnspan=2, sticky="w", padx=(8, 0), pady=(6, 0))
        self.base_swatch = tk.Label(sw, width=3, bd=1, relief="solid")
        self.base_swatch.pack(side="left")
        ttk.Button(sw, text="Choisir…", command=self._pick_base).pack(side="left", padx=4)
        ttk.Button(sw, text="Restaurer", command=lambda: self._set_base("")).pack(side="left")
        self._set_base(self.base_color)
        box = ttk.LabelFrame(f, text="Système et jeux", padding=8)
        box.grid(row=4, column=0, columnspan=2, sticky="ew", pady=(10, 0))
        self.sys_alerts = tk.BooleanVar(value=self.s["sys_alerts"])
        self.disk_free_gb = tk.IntVar(value=self.s["disk_free_gb"])
        self.game_recap = tk.BooleanVar(value=self.s["game_recap"])
        ttk.Checkbutton(box, text="Bandeau quand Windows attend un redémarrage ou qu'un disque "
                                  "est presque plein", variable=self.sys_alerts).grid(
            row=0, column=0, columnspan=3, sticky="w")
        ttk.Label(box, text="Disque presque plein sous").grid(row=1, column=0, sticky="w",
                                                             padx=(22, 0), pady=4)
        ttk.Spinbox(box, from_=1, to=200, width=5, textvariable=self.disk_free_gb).grid(
            row=1, column=1, sticky="w", padx=6)
        ttk.Label(box, text="Go libres", style="Muted.TLabel").grid(row=1, column=2, sticky="w")
        ttk.Checkbutton(box, text="Récapitulatif sur le G19 à la fin d'une partie",
                        variable=self.game_recap).grid(row=2, column=0, columnspan=3,
                                                       sticky="w", pady=(4, 0))
        ttk.Label(f, style="Muted.TLabel", wraplength=330, justify="left",
                  text="Dans Logitech Gaming Software, l'option « Autoriser les jeux à contrôler "
                       "l'éclairage » doit être cochée.").grid(row=5, column=0, columnspan=2,
                                                               sticky="w", pady=(8, 0))

    def _tab_shortcuts(self, nb):
        f = self._tab(nb, "Raccourcis")
        ttk.Label(f, text="Applis à ouvrir depuis le menu du G19 (touche Menu) :").grid(
            row=0, column=0, columnspan=3, sticky="w")
        self.sc_tree = ttk.Treeview(f, columns=("target",), show="tree headings", height=6,
                                    selectmode="browse")
        self.sc_tree.heading("#0", text="Nom")
        self.sc_tree.heading("target", text="Cible")
        self.sc_tree.column("#0", width=140)
        self.sc_tree.column("target", width=200)
        self.sc_tree.grid(row=1, column=0, columnspan=3, sticky="ew", pady=4)
        self._shortcuts = [dict(sc) for sc in self.s["shortcuts"]]
        self._refresh_shortcuts()
        self.sc_tree.bind("<<TreeviewSelect>>", self._on_shortcut)

        self.sc_name, self.sc_target, self.sc_args = tk.StringVar(), tk.StringVar(), tk.StringVar()
        for i, (label, var) in enumerate((("Nom", self.sc_name), ("Cible", self.sc_target),
                                          ("Arguments", self.sc_args))):
            ttk.Label(f, text=label).grid(row=2 + i, column=0, sticky="w", pady=2)
            ttk.Entry(f, textvariable=var, width=30).grid(row=2 + i, column=1, sticky="w")
        ttk.Button(f, text="Parcourir…", command=self._browse_exe).grid(row=3, column=2, padx=6)

        btns = ttk.Frame(f)
        btns.grid(row=5, column=0, columnspan=3, sticky="w", pady=(8, 0))
        for text, cmd in (("Ajouter", self._add_shortcut), ("Modifier", self._edit_shortcut),
                          ("Supprimer", self._del_shortcut), ("▲", lambda: self._move_shortcut(-1)),
                          ("▼", lambda: self._move_shortcut(1)), ("Tester", self._test_shortcut)):
            ttk.Button(btns, text=text, command=cmd).pack(side="left", padx=(0, 4))
        ttk.Label(f, style="Muted.TLabel", wraplength=340, justify="left",
                  text="Cible : un .exe, un dossier, une adresse web ou un lien d'appli "
                       "(discord://, spotify:, steam://rungameid/730…). En plus, le menu propose "
                       "toujours l'appli liée à la page affichée (Discord, lecteur média, "
                       "dernier jeu, Afterburner…).").grid(row=6, column=0, columnspan=3,
                                                          sticky="w", pady=(10, 0))

    def _refresh_shortcuts(self, select=None):
        self.sc_tree.delete(*self.sc_tree.get_children())
        for i, sc in enumerate(self._shortcuts):
            self.sc_tree.insert("", "end", iid=str(i), text=sc["name"],
                                values=(sc["target"] + (f" {sc['args']}" if sc.get("args") else ""),))
        if select is not None and 0 <= select < len(self._shortcuts):
            self.sc_tree.selection_set(str(select))

    def _selected_shortcut(self):
        sel = self.sc_tree.selection()
        return int(sel[0]) if sel else None

    def _on_shortcut(self, _event=None):
        i = self._selected_shortcut()
        if i is not None:
            sc = self._shortcuts[i]
            self.sc_name.set(sc["name"])
            self.sc_target.set(sc["target"])
            self.sc_args.set(sc.get("args", ""))

    def _form_shortcut(self):
        name, target = self.sc_name.get().strip(), self.sc_target.get().strip()
        if not name or not target:
            self._flash("Renseigne un nom et une cible.")
            return None
        return {"name": name, "target": target, "args": self.sc_args.get().strip()}

    def _add_shortcut(self):
        sc = self._form_shortcut()
        if sc:
            self._shortcuts.append(sc)
            self._refresh_shortcuts(len(self._shortcuts) - 1)

    def _edit_shortcut(self):
        i, sc = self._selected_shortcut(), self._form_shortcut()
        if i is not None and sc:
            self._shortcuts[i] = sc
            self._refresh_shortcuts(i)

    def _del_shortcut(self):
        i = self._selected_shortcut()
        if i is not None:
            del self._shortcuts[i]
            self._refresh_shortcuts(min(i, len(self._shortcuts) - 1))

    def _move_shortcut(self, step):
        i = self._selected_shortcut()
        if i is not None and 0 <= i + step < len(self._shortcuts):
            s = self._shortcuts
            s[i], s[i + step] = s[i + step], s[i]
            self._refresh_shortcuts(i + step)

    def _test_shortcut(self):
        sc = self._form_shortcut()
        if sc:
            try:
                launch(sc["target"], sc["args"])
            except OSError as e:
                self._flash(f"Impossible d'ouvrir : {e}")

    def _browse_exe(self):
        path = filedialog.askopenfilename(title="Choisir une appli",
                                          filetypes=[("Programmes", "*.exe *.lnk"), ("Tout", "*.*")])
        if path:
            self.sc_target.set(str(Path(path)))
            if not self.sc_name.get().strip():
                self.sc_name.set(Path(path).stem)

    def _pulse_slider(self, parent, var, rng=None):
        """Curseur de vitesse : à gauche rapide, à droite lent, avec la valeur en ms."""
        lo, hi = rng or settings.PULSE_RANGE
        frame = ttk.Frame(parent)
        ttk.Label(frame, text="rapide", style="Muted.TLabel").pack(side="left")
        value = ttk.Label(frame, width=8)

        def moved(v):
            ms = int(round(float(v) / 5) * 5)
            var.set(ms)
            value.config(text=f"{ms} ms")

        ttk.Scale(frame, from_=lo, to=hi, orient="horizontal", length=170, variable=var,
                  command=moved).pack(side="left", padx=4)
        ttk.Label(frame, text="lent", style="Muted.TLabel").pack(side="left")
        value.pack(side="left", padx=(8, 0))
        value.config(text=f"{var.get()} ms")
        var.trace_add("write", lambda *_: value.config(text=f"{var.get()} ms"))
        return frame

    def _test_pulse(self, kind):
        """Pulsation jouée quelques secondes par l'appli (vitesse enregistrée)."""
        if not instance.is_running():
            self._flash("L'appli doit tourner pour piloter le clavier.")
            return
        config.save("flash_test.json", {"kind": kind, "at": time.time(),
                                        "ms": settings.pulse_ms(self.pulse_ms.get(), 300),
                                        "color": self.colors.get("color_" + kind)})
        self._flash("Pulsation envoyée au clavier pendant 6 s, à la vitesse du curseur.")

    def _test_flash(self, key):
        """Demande à l'appli (qui pilote le clavier) de jouer ce clignotement, avec les valeurs
        affichées ici, même non enregistrées."""
        kind = key.replace("backlight_", "").replace("notif_", "").replace("notifs", "notif")
        blink_key = {"done": "blinks_done", "discord": "blinks_discord"}.get(kind, "blinks_notifs")
        if not instance.is_running():
            self._flash("L'appli doit tourner pour piloter le clavier.")
            return
        if not self.backlight["backlight"].get():
            self._flash("Active d'abord le rétroéclairage (case du haut).")
            return
        config.save("flash_test.json", {"kind": kind, "at": time.time(),
                                        "count": self._int(self.blinks[blink_key], 3, 1, 10),
                                        "ms": settings.blink_ms(self.blink_ms.get()),
                                        "color": self.colors.get(COLOR_OF[key])})
        self._flash("Test envoyé au clavier…")

    def _pick_color(self, key, swatch):
        _rgb, color = colorchooser.askcolor(color=self.colors.get(key) or "#ffffff", parent=self,
                                            title="Couleur de l'effet")
        if color:
            self.colors[key] = color.lower()
            swatch.config(bg=color)
            self._update_dirty()

    def _set_base(self, color):
        self.base_color = color
        self.base_swatch.config(bg=color or theme.FIELD_, text="" if color else "—",
                                fg=theme.MUTED_)

    def _pick_base(self):
        rgb, color = colorchooser.askcolor(color=self.base_color or "#ffffff",
                                           title="Couleur du clavier au repos")
        if color:
            self._set_base(color.lower())

    def _tab_audio(self, nb):
        f = self._tab(nb, "Audio")
        ttk.Label(f, wraplength=340, justify="left",
                  text="Profils audio : passer d'un clic du casque aux haut-parleurs (sortie, "
                       "micro et volume).").grid(row=0, column=0, columnspan=3, sticky="w")
        self.ap_tree = ttk.Treeview(f, columns=("out", "vol"), show="tree headings", height=5,
                                    selectmode="browse")
        self.ap_tree.heading("#0", text="Profil")
        self.ap_tree.heading("out", text="Sortie")
        self.ap_tree.heading("vol", text="Volume")
        self.ap_tree.column("#0", width=110)
        self.ap_tree.column("out", width=180)
        self.ap_tree.column("vol", width=60, anchor="e")
        self.ap_tree.grid(row=1, column=0, columnspan=3, sticky="ew", pady=4)
        self._audio_profiles = [dict(p) for p in self.s.get("audio_profiles") or []]
        self._refresh_profiles()
        self.ap_tree.bind("<<TreeviewSelect>>", self._on_profile)

        self.ap_name, self.ap_out, self.ap_in = tk.StringVar(), tk.StringVar(), tk.StringVar()
        self.ap_vol = tk.StringVar(value=AUDIO_KEEP)
        self._devices = ([], [])
        self.ap_out_box = ttk.Combobox(f, textvariable=self.ap_out, state="readonly", width=34)
        self.ap_in_box = ttk.Combobox(f, textvariable=self.ap_in, state="readonly", width=34)
        rows = (("Nom", ttk.Entry(f, textvariable=self.ap_name, width=20)),
                ("Sortie", self.ap_out_box), ("Micro", self.ap_in_box),
                ("Volume", ttk.Combobox(f, textvariable=self.ap_vol, width=10, values=[
                    AUDIO_KEEP, *[str(v) for v in range(0, 101, 5)]])))
        for i, (label, widget) in enumerate(rows):
            ttk.Label(f, text=label).grid(row=2 + i, column=0, sticky="w", pady=2)
            widget.grid(row=2 + i, column=1, columnspan=2, sticky="w")
        btns = ttk.Frame(f)
        btns.grid(row=6, column=0, columnspan=3, sticky="w", pady=(8, 0))
        for text, cmd in (("Ajouter", self._add_profile), ("Modifier", self._edit_profile),
                          ("Supprimer", self._del_profile), ("▲", lambda: self._move_profile(-1)),
                          ("▼", lambda: self._move_profile(1)),
                          ("Appliquer", self._apply_profile),
                          ("Actualiser", self._load_devices)):
            ttk.Button(btns, text=text, command=cmd).pack(side="left", padx=(0, 4))
        ttk.Label(f, style="Muted.TLabel", wraplength=340, justify="left",
                  text="Sans profil créé ici, le G19 propose « Casque » et « Haut-parleurs », "
                       "reconnus tout seuls d'après le nom des sorties. "
                       "Changer de profil : sur l'écran Audio du G19, OK puis ◄ ► (ou OK, "
                       "OK : profil suivant) · menu du G19 · clic droit sur l'icône G19 de la "
                       "barre des tâches → Profil audio. Pense à « Enregistrer » en bas.").grid(
            row=7, column=0, columnspan=3, sticky="w", pady=(10, 0))
        self._load_devices()

    def _load_devices(self):
        def work():
            try:
                devs = volume.list_devices()
            except Exception:
                devs = ([], [])
            self.after(0, lambda: self._set_devices(devs))

        threading.Thread(target=work, daemon=True).start()

    def _set_devices(self, devs):
        self._devices = devs
        self.ap_out_box.config(values=[n for _i, n in devs[0]])
        self.ap_in_box.config(values=[AUDIO_KEEP_IN, *[n for _i, n in devs[1]]])
        if not self.ap_in.get():
            self.ap_in.set(AUDIO_KEEP_IN)

    def _refresh_profiles(self, select=None):
        self.ap_tree.delete(*self.ap_tree.get_children())
        for i, p in enumerate(self._audio_profiles):
            vol = "—" if p.get("volume") is None else f"{p['volume']} %"
            self.ap_tree.insert("", "end", iid=str(i), text=p["name"],
                                values=(p.get("out") or "—", vol))
        if select is not None and 0 <= select < len(self._audio_profiles):
            self.ap_tree.selection_set(str(select))

    def _selected_profile(self):
        sel = self.ap_tree.selection()
        return int(sel[0]) if sel else None

    def _on_profile(self, _event=None):
        i = self._selected_profile()
        if i is not None:
            p = self._audio_profiles[i]
            self.ap_name.set(p["name"])
            self.ap_out.set(p.get("out") or "")
            self.ap_in.set(p.get("in") or AUDIO_KEEP_IN)
            self.ap_vol.set(AUDIO_KEEP if p.get("volume") is None else str(p["volume"]))

    def _form_profile(self):
        name, out = self.ap_name.get().strip(), self.ap_out.get().strip()
        if not name or not out:
            self._flash("Renseigne un nom et une sortie.")
            return None
        mic = self.ap_in.get().strip()
        mic = "" if mic == AUDIO_KEEP_IN else mic
        try:
            vol = None if self.ap_vol.get().strip() in ("", AUDIO_KEEP) else \
                max(0, min(100, int(self.ap_vol.get())))
        except ValueError:
            self._flash("Volume : un nombre de 0 à 100, ou « inchangé ».")
            return None

        def dev_id(devs, n):
            return next((i for i, dn in devs if dn == n), "")

        return {"name": name, "out": out, "out_id": dev_id(self._devices[0], out),
                "in": mic, "in_id": dev_id(self._devices[1], mic) if mic else "", "volume": vol}

    def _add_profile(self):
        p = self._form_profile()
        if p:
            self._audio_profiles.append(p)
            self._refresh_profiles(len(self._audio_profiles) - 1)

    def _edit_profile(self):
        i, p = self._selected_profile(), self._form_profile()
        if i is not None and p:
            self._audio_profiles[i] = p
            self._refresh_profiles(i)

    def _del_profile(self):
        i = self._selected_profile()
        if i is not None:
            del self._audio_profiles[i]
            self._refresh_profiles(min(i, len(self._audio_profiles) - 1))

    def _move_profile(self, step):
        i = self._selected_profile()
        if i is not None and 0 <= i + step < len(self._audio_profiles):
            s = self._audio_profiles
            s[i], s[i + step] = s[i + step], s[i]
            self._refresh_profiles(i + step)

    def _apply_profile(self):
        p = self._form_profile()
        if not p:
            return

        def work():
            try:
                import comtypes
                comtypes.CoInitialize()
                try:
                    ok, text = volume.apply_profile(p)
                finally:
                    comtypes.CoUninitialize()
            except Exception as e:
                text = str(e) or e.__class__.__name__
            self.after(0, lambda: self._flash(f"Profil « {p['name']} » : {text}"))

        threading.Thread(target=work, daemon=True).start()

    def _tab_fuel(self, nb):
        f = self._tab(nb, "Carburant")
        ttk.Label(f, justify="left", wraplength=360, text=(
            "Les prix viennent de l'intégration « Prix Carburant » de Home Assistant : toutes "
            "ses stations s'affichent sur la page Carburant du G19.\n\n"
            "1. Dans Home Assistant : ton profil → Sécurité → Jetons d'accès longue durée → "
            "Créer un jeton.\n"
            "2. Colle l'adresse de Home Assistant et le jeton ici, puis « Enregistrer et "
            "tester ».\n"
            "Le jeton reste sur ce PC (dossier des données) et n'est envoyé qu'à cette "
            "adresse.")).grid(row=0, column=0, columnspan=2, sticky="w")
        url, token = fuel.load_ha()
        self.ha_url, self.ha_token = tk.StringVar(value=url), tk.StringVar(value=token)
        ttk.Label(f, text="Adresse").grid(row=1, column=0, sticky="w", pady=(10, 2))
        ttk.Entry(f, textvariable=self.ha_url, width=36).grid(row=1, column=1, sticky="w",
                                                              pady=(10, 2))
        ttk.Label(f, text="Jeton").grid(row=2, column=0, sticky="w", pady=2)
        ttk.Entry(f, textvariable=self.ha_token, width=36, show="•").grid(row=2, column=1,
                                                                         sticky="w")
        btns = ttk.Frame(f)
        btns.grid(row=3, column=0, columnspan=2, sticky="w", pady=8)
        ttk.Button(btns, text="Enregistrer et tester", command=self._save_ha).pack(side="left")
        ttk.Button(btns, text="Ouvrir la page des jetons", command=self._open_ha_tokens).pack(
            side="left", padx=6)
        self.ha_state = ttk.Label(f, text="", wraplength=360, justify="left")
        self.ha_state.grid(row=4, column=0, columnspan=2, sticky="w")
        self.fuel_main = tk.StringVar(value=FUEL_MAIN.get(self.s["fuel_main"], FUEL_AUTO))
        ttk.Label(f, text="Mis en avant").grid(row=5, column=0, sticky="w", pady=(12, 2))
        ttk.Combobox(f, textvariable=self.fuel_main, state="readonly", width=16,
                     values=list(FUEL_MAIN.values())).grid(row=5, column=1, sticky="w",
                                                           pady=(12, 2))
        ttk.Label(f, style="Muted.TLabel", wraplength=360, justify="left",
                  text="Carburant dont le prix le plus bas s'affiche en grand en haut de la "
                       "page (automatique : celui que le plus de stations vendent). Pense à "
                       "« Enregistrer » en bas pour ce choix.").grid(
            row=6, column=0, columnspan=2, sticky="w")

    def _open_ha_tokens(self):
        url = self.ha_url.get().strip().rstrip("/")
        if url:
            webbrowser.open(f"{url}/profile/security")
        else:
            self.ha_state.config(text="Renseigne d'abord l'adresse de Home Assistant.")

    def _save_ha(self):
        url, token = self.ha_url.get().strip().rstrip("/"), self.ha_token.get().strip()
        if url and not url.startswith(("http://", "https://")):
            url = "https://" + url
            self.ha_url.set(url)
        fuel.save_ha(url, token)
        if not (url and token):
            self.ha_state.config(text="Accès oublié." if not (url or token) else
                                 "Il faut l'adresse et le jeton.")
            return
        self.ha_state.config(text="Test en cours…")

        def work():
            try:
                stations = fuel.parse_states(fuel.fetch_states(url, token))
                prices = sum(len(s["fuels"]) for s in stations.values())
                text = (f"Connecté : {len(stations)} station(s), {prices} prix. La page "
                        "Carburant du G19 se met à jour dans la minute." if stations else
                        "Connecté, mais aucune station « Prix Carburant » trouvée.")
            except urllib.error.HTTPError as e:
                msg = fuel.http_error_text(e)
                text = msg[0].upper() + msg[1:] + "."
            except Exception as e:
                text = f"Home Assistant injoignable : {e.__class__.__name__}"
            self.after(0, lambda: self.ha_state.config(text=text))

        threading.Thread(target=work, daemon=True).start()

    def _tab_discord(self, nb):
        f = self._tab(nb, "Discord")
        steps = ("1. Crée une application sur le portail développeur Discord.\n"
                 "2. Onglet OAuth2 : copie le Client ID et le Client Secret.\n"
                 "3. OAuth2 → Redirects : ajoute  http://localhost  puis Save.\n"
                 "4. Colle-les ici et clique sur « Autoriser » : accepte la\n"
                 "    fenêtre qui s'ouvre dans Discord.")
        ttk.Label(f, text=steps, justify="left").grid(row=0, column=0, columnspan=2, sticky="w")
        ttk.Button(f, text="Ouvrir le portail développeur",
                   command=lambda: webbrowser.open(PORTAL)).grid(row=1, column=0, sticky="w",
                                                                 pady=8)
        cfg = config.load(discord_rpc.CONFIG_FILE, {}) or {}
        self.client_id = tk.StringVar(value=cfg.get("client_id", ""))
        self.client_secret = tk.StringVar(value=cfg.get("client_secret", ""))
        ttk.Label(f, text="Client ID").grid(row=2, column=0, sticky="w")
        ttk.Entry(f, textvariable=self.client_id, width=36).grid(row=2, column=1, sticky="w")
        ttk.Label(f, text="Client Secret").grid(row=3, column=0, sticky="w", pady=4)
        ttk.Entry(f, textvariable=self.client_secret, width=36, show="•").grid(row=3, column=1,
                                                                             sticky="w")
        btns = ttk.Frame(f)
        btns.grid(row=4, column=0, columnspan=2, sticky="w", pady=8)
        ttk.Button(btns, text="Autoriser dans Discord", command=self._authorize).pack(side="left")
        ttk.Button(btns, text="Oublier l'accès", command=self._forget).pack(side="left", padx=6)
        self.discord_state = ttk.Label(f, text="", wraplength=330, justify="left")
        self.discord_state.grid(row=5, column=0, columnspan=2, sticky="w")
        self._refresh_discord_state()

    def _tab_steam(self, nb):
        f = self._tab(nb, "Steam")
        ttk.Label(f, justify="left", text=(
            "Les téléchargements et mises à jour en cours s'affichent sans rien régler.\n"
            "\n"
            "Pour voir tes amis en ligne, il faut ta clé d'API Web Steam :\n"
            "1. Ouvre la page de la clé (connecte-toi à Steam), nom de domaine : localhost.\n"
            "2. Copie la clé ici puis « Enregistrer la clé ».\n"
            "La clé reste sur ce PC (dossier des données) et n'est envoyée qu'à Steam.\n"
            "Ta liste d'amis doit être visible (Confidentialité du profil).")).grid(
            row=0, column=0, columnspan=2, sticky="w")
        ttk.Button(f, text="Ouvrir la page de la clé",
                   command=lambda: webbrowser.open("https://steamcommunity.com/dev/apikey")).grid(
            row=1, column=0, sticky="w", pady=8)
        self.steam_key = tk.StringVar(value=steam_live.load_key())
        ttk.Label(f, text="Clé API").grid(row=2, column=0, sticky="w")
        ttk.Entry(f, textvariable=self.steam_key, width=36, show="•").grid(row=2, column=1,
                                                                         sticky="w")
        btns = ttk.Frame(f)
        btns.grid(row=3, column=0, columnspan=2, sticky="w", pady=8)
        ttk.Button(btns, text="Enregistrer la clé", command=self._save_steam_key).pack(side="left")
        ttk.Button(btns, text="Oublier la clé",
                   command=lambda: (self.steam_key.set(""), self._save_steam_key())).pack(
            side="left", padx=6)
        self.steam_state = ttk.Label(f, text="", wraplength=330, justify="left")
        self.steam_state.grid(row=4, column=0, columnspan=2, sticky="w")

    def _save_steam_key(self):
        steam_live.save_key(self.steam_key.get())
        self.steam_state.config(text="Clé enregistrée : l'écran Steam du G19 se met à jour dans"
                                     " la minute." if self.steam_key.get().strip()
                                else "Clé oubliée.")

    def _tab_system(self, nb):
        f = self._tab(nb, "Système")
        box = ttk.LabelFrame(f, text="Appli", padding=8)
        box.grid(row=0, column=0, sticky="ew")
        ttk.Button(box, text="Démarrer", command=lambda: self._control("start")).grid(
            row=0, column=0)
        ttk.Button(box, text="Redémarrer", command=lambda: self._control("restart")).grid(
            row=0, column=1, padx=6)
        ttk.Button(box, text="Arrêter", command=lambda: self._control("stop")).grid(
            row=0, column=2)

        self.startup = tk.BooleanVar(value=install_startup.is_installed())
        self.hooks = tk.BooleanVar(value=install_hooks.is_installed())
        ttk.Checkbutton(f, text="Lancer au démarrage de Windows", variable=self.startup,
                        command=lambda: self._apply_flag(install_startup, self.startup)).grid(
            row=1, column=0, sticky="w", pady=(10, 0))
        ttk.Checkbutton(f, text="Voyant Claude (hooks dans ~/.claude/settings.json)",
                        variable=self.hooks,
                        command=lambda: self._apply_flag(install_hooks, self.hooks)).grid(
            row=2, column=0, sticky="w", pady=(4, 0))

        box = ttk.LabelFrame(f, text="Ventilateurs carte mère (via LibreHardwareMonitor)",
                             padding=8)
        box.grid(row=5, column=0, sticky="ew", pady=(10, 0))
        self._fan_ids = {v: k for k, v in FAN_LABELS.items()}
        self.fan_profile = tk.StringVar(value=FAN_LABELS.get(self.s["fan_profile"], "auto (GCC)"))
        ttk.Label(box, text="Profil").grid(row=0, column=0, sticky="w")
        ttk.Combobox(box, textvariable=self.fan_profile, values=list(FAN_LABELS.values()),
                     state="readonly", width=14).grid(row=0, column=1, sticky="w", padx=8)
        self.fan_safe_cpu = tk.IntVar(value=self.s["fan_safe_cpu"])
        self.fan_safe_gpu = tk.IntVar(value=self.s["fan_safe_gpu"])
        ttk.Label(box, text="Retour en auto si CPU ≥ (°C)").grid(row=1, column=0, sticky="w",
                                                                 pady=(6, 0))
        ttk.Spinbox(box, from_=60, to=100, width=6, textvariable=self.fan_safe_cpu).grid(
            row=1, column=1, sticky="w", padx=8, pady=(6, 0))
        ttk.Label(box, text="ou hotspot GPU ≥ (°C)").grid(row=2, column=0, sticky="w", pady=4)
        ttk.Spinbox(box, from_=60, to=100, width=6, textvariable=self.fan_safe_gpu).grid(
            row=2, column=1, sticky="w", padx=8)
        self.fan_recover = tk.IntVar(value=self.s["fan_recover_seconds"])
        ttk.Label(box, text="Retour au profil, refroidi depuis (s)").grid(row=4, column=0,
                                                                           sticky="w", pady=4)
        ttk.Spinbox(box, from_=10, to=900, increment=10, width=6,
                    textvariable=self.fan_recover).grid(row=4, column=1, sticky="w", padx=8)
        ttk.Label(box, style="Muted.TLabel", wraplength=330, justify="left",
                  text="Hors « auto », remplace les courbes de GCC par une vitesse fixe (30 % "
                       "minimum). La pompe n'est jamais touchée. Retour en auto au-delà des "
                       "seuils ci-dessus (sauf profil maximum), le temps que ça refroidisse : "
                       "le profil revient seul une fois CPU et GPU 8 °C sous les seuils pendant "
                       "la durée ci-dessous. Auto aussi à la fermeture de l'appli.").grid(
            row=3, column=0, columnspan=2, sticky="w", pady=(6, 0))
        box = ttk.LabelFrame(f, text="Sources de données", padding=8)
        box.grid(row=3, column=0, sticky="ew", pady=(10, 0))
        self.sources = ttk.Label(box, text="…", justify="left", font=("Consolas", 9))
        self.sources.pack(anchor="w")

        btns = ttk.Frame(f)
        btns.grid(row=4, column=0, sticky="w", pady=(10, 0))
        ttk.Button(btns, text="Journal", command=lambda: self._open(APP_DIR / "g19.log")).pack(
            side="left")
        ttk.Button(btns, text="Données", command=lambda: self._open(config.DATA_DIR)).pack(
            side="left", padx=4)
        ttk.Button(btns, text="Historique des débits",
                   command=lambda: self._open(config.DATA_DIR / "speedtests.csv")).pack(
            side="left", padx=(0, 4))
        ttk.Button(btns, text="Dossier de l'appli", command=lambda: self._open(APP_DIR)).pack(
            side="left")

        box = ttk.LabelFrame(f, text="Sauvegarde des réglages", padding=8)
        box.grid(row=6, column=0, sticky="ew", pady=(10, 0))
        self.bk_secrets = tk.BooleanVar(value=True)
        self.bk_history = tk.BooleanVar(value=True)
        ttk.Checkbutton(box, text="Inclure les accès Discord et la clé Steam",
                        variable=self.bk_secrets).grid(row=0, column=0, columnspan=2, sticky="w")
        ttk.Checkbutton(box, text="Inclure les historiques (jeux, débits, 24 h)",
                        variable=self.bk_history).grid(row=1, column=0, columnspan=2, sticky="w")
        line = ttk.Frame(box)
        line.grid(row=2, column=0, columnspan=2, sticky="w", pady=(6, 0))
        ttk.Button(line, text="Exporter…", style="Accent.TButton",
                   command=self._export_backup).pack(side="left")
        ttk.Button(line, text="Importer…", command=self._import_backup).pack(side="left", padx=6)
        ttk.Label(box, style="Muted.TLabel", wraplength=330, justify="left",
                  text="Un fichier .zip à garder avant une réinstallation. À l'import, l'état "
                       "actuel est d'abord sauvegardé dans le dossier des données, puis l'appli "
                       "redémarre.").grid(row=3, column=0, columnspan=2, sticky="w", pady=(6, 0))

        box = ttk.LabelFrame(f, text="Mises à jour", padding=8)
        box.grid(row=7, column=0, sticky="ew", pady=(10, 0))
        self.auto_update = tk.BooleanVar(value=self.s["auto_update"])
        ttk.Checkbutton(box, text="Se mettre à jour depuis GitHub (toutes les 15 min)",
                        variable=self.auto_update).grid(row=0, column=0, sticky="w")
        ttk.Button(box, text="Vérifier maintenant", command=self._check_update).grid(
            row=0, column=1, padx=(8, 0))
        ttk.Label(box, style="Muted.TLabel", wraplength=330, justify="left",
                  text="Le dossier de l'appli est une copie du dépôt GitHub. S'il y a des "
                       "modifications locales non envoyées, rien n'est écrasé : un bandeau "
                       "prévient sur le G19.").grid(row=1, column=0, columnspan=2, sticky="w",
                                                    pady=(6, 0))

    # --- actions ---

    def _check_update(self):
        if not instance.is_running():
            self._flash("L'appli doit tourner pour vérifier les mises à jour.")
            return
        config.save("flash_test.json", {"kind": "update", "at": time.time()})
        self._flash("Vérification demandée : le résultat s'affiche sur le G19.")

    def collect(self):
        enabled = [iid for iid in self.tree.get_children() if self.tree.set(iid, "on")]
        return {
            "pages": enabled or ["system"],
            "remember_page": self.remember.get(),
            "start_page": BY_TITLE.get(self.start_page.get(), "system"),
            "game_page": {v: k for k, v in GAME_PAGES.items()}.get(self.game_page.get(), "gpu"),
            "fps": self._int(self.fps, 30, 2, 60),
            "gpu_power_max": self._int(self.power, 315, 100, 700),
            "discord_toasts": self.toasts.get(),
            "toast_seconds": self._int(self.toast_s, 6, 2, 30),
            "claude_strip_seconds": self._int(self.strip_s, 10, 0, 600),
            "win_toasts": self.win_toasts.get(),
            "media_toasts": self.media_toasts.get(),
            "device_toasts": self.device_toasts.get(),
            "ping_target": self.ping_target.get().strip() or "1.1.1.1",
            "steam_toasts": self.steam_toasts.get(),
            "voice_toasts": self.voice_toasts.get(),
            "stream_toasts": self.stream_toasts.get(),
            "docker_toasts": self.docker_toasts.get(),
            "page_toasts": self.page_toasts.get(),
            "driver_toasts": self.driver_toasts.get(),
            "auto_update": self.auto_update.get(),
            "idle_screen": self.idle_screen.get(),
            "idle_minutes": self._int(self.idle_minutes, 5, 1, 120),
            "away_summary": self.away_summary.get(),
            "away_min_minutes": self._int(self.away_min, 5, 0, 240),
            "sys_alerts": self.sys_alerts.get(),
            "screen_brightness": self._int(self.scr_brightness, 100, 50, 150),
            "screen_contrast": self._int(self.scr_contrast, 100, 50, 150),
            "screen_gamma": self._int(self.scr_gamma, 100, 60, 160),
            "screen_saturation": self._int(self.scr_saturation, 100, 0, 200),
            "screen_sharpen": self.scr_sharpen.get(),
            "disk_free_gb": self._int(self.disk_free_gb, 15, 1, 200),
            "game_recap": self.game_recap.get(),
            "night_mode": self.night_mode.get(),
            "night_start": self.night_start.get() or "23:00",
            "night_end": self.night_end.get() or "07:00",
            "night_dim": self._int(self.night_dim, 40, 10, 100),
            "night_theme": {v: k for k, v in NIGHT_THEMES.items()}.get(self.night_theme.get(), ""),
            "night_quiet": self.night_quiet.get(),
            "theme": {v: k for k, v in THEME_LABELS.items()}.get(self.theme.get(), "dark"),
            "wallpaper_bg": self.wallpaper_bg.get(),
            "wallpaper_dim": self._int(self.wallpaper_dim, 60, 0, 90),
            "notif_ignore": [a.strip() for a in self.notif_ignore.get().split(",") if a.strip()],
            "shortcuts": self._shortcuts,
            "audio_profiles": self._audio_profiles,
            "fuel_main": {v: k for k, v in FUEL_MAIN.items()}.get(self.fuel_main.get(), ""),
            "fuel_toasts": self.fuel_toasts.get(),
            "weather_city": self.city.get().strip(),
            "alerts_on": self.alerts_on.get(),
            "alerts": {k: self._int(v, DEFAULT_THRESHOLDS[k], 0, 120)
                       for k, v in self.thresholds.items()},
            **{k: v.get() for k, v in self.backlight.items()},
            **{k: self._int(v, 3, 1, 10) for k, v in self.blinks.items()},
            "blink_ms": settings.blink_ms(self.blink_ms.get()),
            **{k: v for k, v in self.colors.items()},
            "pulse_ms": settings.pulse_ms(self.pulse_ms.get(), 300),
            "fan_profile": self._fan_ids.get(self.fan_profile.get(), "auto"),
            "fan_safe_cpu": self._int(self.fan_safe_cpu, 85, 60, 100),
            "fan_safe_gpu": self._int(self.fan_safe_gpu, 95, 60, 100),
            "fan_recover_seconds": self._int(self.fan_recover, 60, 10, 900),
            "backlight_base": self.base_color,
        }

    @staticmethod
    def _int(var, default, lo, hi):
        try:
            return max(lo, min(hi, int(var.get())))
        except (tk.TclError, ValueError):
            return default

    def save(self):
        cur = self.collect()
        changes = {k: v for k, v in cur.items() if v != self._base.get(k)}
        if not changes:
            self._flash("Rien à enregistrer.")
            return
        settings.save_changes(changes)
        self._watch.poll()
        self._base = cur
        self._update_dirty()
        self._flash("Enregistré — l'écran du G19 est mis à jour.")

    def close(self):
        """Ferme la fenêtre ; propose d'enregistrer s'il reste des modifications."""
        cur = self.collect()
        dirty = [k for k, v in cur.items() if v != self._base.get(k)]
        if dirty:
            answer = messagebox.askyesnocancel(
                "G19 Monitor", "Enregistrer les modifications avant de fermer ?", parent=self)
            if answer is None:
                return
            if answer:
                self.save()
        self.destroy()

    def _sync_from_file(self):
        """Reprend dans la fenêtre les réglages changés ailleurs (menu du G19…), sauf ceux
        modifiés ici et pas encore enregistrés."""
        if not self._watch.poll():
            return
        s, cur = self._watch.settings, self.collect()
        dirty = {k for k, v in cur.items() if v != self._base.get(k)}
        simple = {"remember_page": self.remember, "fps": self.fps, "gpu_power_max": self.power,
                  "discord_toasts": self.toasts, "toast_seconds": self.toast_s,
                  "claude_strip_seconds": self.strip_s, "win_toasts": self.win_toasts,
                  "media_toasts": self.media_toasts, "device_toasts": self.device_toasts,
                  "ping_target": self.ping_target, "steam_toasts": self.steam_toasts,
                  "voice_toasts": self.voice_toasts,
                  "stream_toasts": self.stream_toasts, "docker_toasts": self.docker_toasts,
                  "fuel_toasts": self.fuel_toasts,
                  "page_toasts": self.page_toasts, "driver_toasts": self.driver_toasts,
                  "auto_update": self.auto_update,
                  "wallpaper_bg": self.wallpaper_bg, "wallpaper_dim": self.wallpaper_dim,
                  "idle_screen": self.idle_screen, "idle_minutes": self.idle_minutes,
                  "away_summary": self.away_summary, "away_min_minutes": self.away_min,
                  "fan_safe_cpu": self.fan_safe_cpu, "fan_safe_gpu": self.fan_safe_gpu,
                  "fan_recover_seconds": self.fan_recover,
                  "sys_alerts": self.sys_alerts, "disk_free_gb": self.disk_free_gb,
                  "screen_brightness": self.scr_brightness, "screen_contrast": self.scr_contrast,
                  "screen_gamma": self.scr_gamma, "screen_saturation": self.scr_saturation,
                  "screen_sharpen": self.scr_sharpen,
                  "game_recap": self.game_recap,
                  "night_mode": self.night_mode, "night_start": self.night_start,
                  "night_end": self.night_end, "night_dim": self.night_dim,
                  "night_quiet": self.night_quiet,
                  "alerts_on": self.alerts_on, "blink_ms": self.blink_ms,
                  "pulse_ms": self.pulse_ms,
                  **self.backlight, **self.blinks}
        changed = []
        for key, var in simple.items():
            if key not in dirty and s.get(key) != cur.get(key):
                var.set(s[key])
                changed.append(key)
        if "fan_profile" not in dirty and s["fan_profile"] != cur["fan_profile"]:
            self.fan_profile.set(FAN_LABELS.get(s["fan_profile"], "auto (GCC)"))
            changed.append("fan_profile")
        if "night_theme" not in dirty and s["night_theme"] != cur["night_theme"]:
            self.night_theme.set(NIGHT_THEMES.get(s["night_theme"], "inchangé"))
            changed.append("night_theme")
        if "theme" not in dirty and theme_of(s) != cur["theme"]:
            self.theme.set(THEME_LABELS[theme_of(s)])
            self._restyle(theme_of(s))
            changed.append("theme")
        if "game_page" not in dirty and s["game_page"] != cur["game_page"]:
            self.game_page.set(GAME_PAGES.get(s["game_page"], "GPU"))
            changed.append("game_page")
        for key, sw in self.color_swatches.items():
            if key not in dirty and s.get(key) and s[key] != cur.get(key):
                self.colors[key] = s[key]
                sw.config(bg=s[key])
                changed.append(key)
        if "backlight_base" not in dirty and s["backlight_base"] != cur["backlight_base"]:
            self._set_base(s["backlight_base"])
            changed.append("backlight_base")
        self.s = s
        for key in changed:
            self._base[key] = self.collect()[key]
        if changed:
            self._flash("Réglages mis à jour depuis le G19.")

    def _flash(self, text):
        self.status.config(text=text)
        self.after(5000, lambda: self.status.config(text="") if self.status["text"] == text else None)

    def _on_select(self, _event=None):
        sel = self.tree.selection()
        if sel:
            self.preview_page.set(TITLES[sel[0]])

    def _toggle_page(self):
        for iid in self.tree.selection():
            self.tree.set(iid, "on", "" if self.tree.set(iid, "on") else "✔")

    def _move(self, step):
        for iid in self.tree.selection():
            self.tree.move(iid, "", max(0, self.tree.index(iid) + step))

    def _authorize(self):
        cid, secret = self.client_id.get().strip(), self.client_secret.get().strip()
        if not cid or not secret:
            self.discord_state.config(text="Renseigne le Client ID et le Client Secret.")
            return
        self.discord_state.config(text="Accepte la demande d'autorisation dans Discord…")

        def work():
            try:
                name = discord_rpc.authorize(cid, secret)
                msg = f"Autorisé pour {name}. L'écran Discord s'activera dans les 15 s."
            except discord_rpc.RpcError as e:
                msg = f"Échec : {e}"
            except Exception as e:
                msg = (f"Échec de l'échange du jeton : {e}\nVérifie le secret et la redirection "
                       f"{discord_rpc.REDIRECT_URI}.")
            self.after(0, lambda: self.discord_state.config(text=msg))

        threading.Thread(target=work, daemon=True).start()

    def _forget(self):
        discord_rpc.forget()
        self._refresh_discord_state()

    def _refresh_discord_state(self):
        cfg = config.load(discord_rpc.CONFIG_FILE, {}) or {}
        if cfg.get("access_token"):
            exp = datetime.fromtimestamp(cfg.get("expires_at", 0)).strftime("%d/%m/%Y")
            text = f"Accès autorisé (renouvelé automatiquement, prochain le {exp})."
        else:
            text = "Pas encore autorisé."
        self.discord_state.config(text=text)

    def _export_backup(self):
        path = filedialog.asksaveasfilename(
            parent=self, title="Exporter les réglages", defaultextension=".zip",
            initialfile=time.strftime("g19_reglages_%Y-%m-%d.zip"),
            filetypes=[("Sauvegarde G19 Monitor", "*.zip")])
        if not path:
            return
        if self._dirty():
            self.save()           # la sauvegarde contient aussi ce qui est affiché ici
        try:
            names = backup.export(path, self.bk_secrets.get(), self.bk_history.get())
        except OSError as e:
            messagebox.showerror("G19 Monitor", f"Export impossible : {e}", parent=self)
            return
        self._flash(f"Exporté ({backup.describe(names)}) : {Path(path).name}")

    def _import_backup(self):
        path = filedialog.askopenfilename(parent=self, title="Importer des réglages",
                                          filetypes=[("Sauvegarde G19 Monitor", "*.zip")])
        if not path:
            return
        try:
            names = backup.inspect(path)
        except (OSError, ValueError, KeyError) as e:
            messagebox.showerror("G19 Monitor", f"Sauvegarde illisible : {e}", parent=self)
            return
        if not messagebox.askyesno(
                "G19 Monitor", f"Remplacer par cette sauvegarde : {backup.describe(names)} ?\n\n"
                "L'état actuel est d'abord sauvegardé dans le dossier des données.", parent=self):
            return
        try:
            _names, safety = backup.restore(path)
        except (OSError, ValueError) as e:
            messagebox.showerror("G19 Monitor", f"Import impossible : {e}", parent=self)
            return
        # l'appli et cette fenêtre repartent sur les réglages importés
        if instance.is_running():
            self._control("restart")
        subprocess.Popen([sys.executable, str(Path(__file__).resolve())])
        messagebox.showinfo("G19 Monitor", f"Importé. Copie de l'état précédent :\n{safety.name}",
                            parent=self)
        self.destroy()

    def _dirty(self):
        cur = self.collect()
        return any(v != self._base.get(k) for k, v in cur.items())

    def _control(self, action):
        def work():
            if action == "stop":
                instance.stop()
            else:
                if action == "restart":
                    instance.stop()
                if not instance.is_running():
                    instance.spawn()

        threading.Thread(target=work, daemon=True).start()
        self._flash({"start": "Démarrage…", "restart": "Redémarrage…", "stop": "Arrêt…"}[action])

    def _apply_flag(self, module, var):
        try:
            module.set_installed(var.get())
        except OSError as e:
            var.set(not var.get())
            self._flash(f"Impossible : {e}")

    @staticmethod
    def _open(path):
        if Path(path).exists():
            os.startfile(path)

    # --- aperçu et états ---

    def _load_ctx(self):
        from g19.media import MediaMonitor
        from g19_monitor import make_ctx

        self.ctx = make_ctx()
        self.media = MediaMonitor()

    def _show_update_status(self):
        """Résultat de la dernière vérification faite par l'appli (fichier d'état)."""
        st = settings.load_state().get("update_status") or {}
        text = st.get("text", "")
        if text:
            text = "Mises à jour : " + text
        if self.update_label.cget("text") != text:
            self.update_label.config(text=text)

    def _tick(self):
        try:
            if time.time() - getattr(self, "_update_at", 0) >= 2:
                self._update_at = time.time()
                self._show_update_status()
            self._update_preview()
            self._update_states()
            self._sync_from_file()
            now = time.time()
            if now - getattr(self, "_dirty_at", 0) >= 0.7:
                self._dirty_at = now
                self._update_dirty()
        finally:
            self.after(100 if self.preview_page.get() == LIVE else 250, self._tick)

    def _keypad(self, parent):
        """Touches du G19 sous l'aperçu : Menu et Annuler à gauche, croix + OK à droite."""
        pad = ttk.Frame(parent, style="Root.TFrame")
        pad.pack(fill="x", pady=(10, 0))
        left = ttk.Frame(pad, style="Root.TFrame")
        left.pack(side="left", anchor="n")
        self._pad_buttons = []

        def key(master, text, button, width=4, **grid):
            b = ttk.Button(master, text=text, width=width, command=lambda: self._press(button))
            b.grid(padx=2, pady=2, **grid)
            self._pad_buttons.append(b)

        key(left, "Menu", "menu", 8, row=0, column=0)
        key(left, "Annuler", "cancel", 8, row=1, column=0)
        cross = ttk.Frame(pad, style="Root.TFrame")
        cross.pack(side="right")
        key(cross, "▲", "up", row=0, column=1)
        key(cross, "◀", "left", row=1, column=0)
        key(cross, "OK", "ok", row=1, column=1)
        key(cross, "▶", "right", row=1, column=2)
        key(cross, "▼", "down", row=2, column=1)
        self.pad_hint = ttk.Label(parent, text="", style="RootMuted.TLabel", justify="center")
        self.pad_hint.pack(pady=(6, 0))

    def _press(self, button):
        if not instance.is_running():
            self._flash("L'appli n'est pas lancée : les touches ne vont nulle part.")
            return
        remote.send_key(button)
        if self.preview_page.get() != LIVE:
            self.preview_page.set(LIVE)    # on montre l'effet de la touche

    def _update_live(self, now):
        """Aperçu « en direct » : l'image que l'appli envoie au G19. False si indisponible."""
        if now - self._last_mirror_req >= 1:
            self._last_mirror_req = now
            remote.request_mirror()
        img = remote.read_mirror()
        if img is None:
            return False
        img = img.resize((int(320 * PREVIEW_SCALE), int(240 * PREVIEW_SCALE)), Image.LANCZOS)
        self._photo = ImageTk.PhotoImage(img)
        self.preview.config(image=self._photo, text="", width=img.width, height=img.height)
        return True

    def _update_preview(self):
        now = time.time()
        live = self.preview_page.get() == LIVE
        running = instance.is_running()
        for b in self._pad_buttons:
            b.state(["!disabled"] if running else ["disabled"])
        self.pad_hint.config(text="clic sur l'écran puis flèches · Entrée = OK · Échap = Annuler"
                                  " · M = Menu" if running else "lance l'appli pour piloter le G19")
        if live and running and self._update_live(now):
            return
        c = self.ctx
        if not c:
            return
        if now - self._last_sample >= 1:
            self._last_sample = now
            c.stats.sample()
            c.gpu.sample(c.stats)
            c.games.update(c.gpu.game, c.gpu.s, now)
            c.sessions = read_sessions(now)
            self._update_sources()
        c.gpu.sample_fps()
        c.media = self.media.state
        cfg = self.collect()
        page = BY_TITLE.get(self.preview_page.get(), cfg["pages"][0])
        if page not in cfg["pages"]:
            cfg["pages"] = cfg["pages"] + [page]
        c.settings = {**settings.DEFAULTS, **cfg}
        img = screen.adjust(render(page, c, now), c.settings)
        img = img.resize((int(320 * PREVIEW_SCALE), int(240 * PREVIEW_SCALE)), Image.LANCZOS)
        self._photo = ImageTk.PhotoImage(img)
        self.preview.config(image=self._photo, text="", width=img.width, height=img.height)

    def _update_states(self):
        running = instance.is_running()
        self.header.set_state("● en cours d'exécution" if running else "○ arrêtée",
                              "OK" if running else None)

    def _restyle(self, name):
        if name != theme.NAME:
            theme.apply(self, name)
            self._set_base(self.base_color)
            self.nav.refresh()

    def _update_dirty(self):
        dirty = self._dirty()
        self.dirty_label.config(text="● modifications non enregistrées" if dirty else "")

    def _update_sources(self):
        c = self.ctx
        ok = lambda b: "✔" if b else "✘"  # noqa: E731
        steam = c.games.steam
        lines = [
            f"{ok(afterburner.read_sensors() is not None)} MSI Afterburner",
            f"{ok(rtss.read_apps() is not None)} RivaTuner (FPS)",
            f"{ok(bool(c.gpu.lhm.sensors))} LibreHardwareMonitor",
            f"{ok(steam and steam.apps)} Steam" + (f" ({len(steam.apps)} jeux)" if steam else ""),
            f"{ok(c.discord.status == 'connecté')} Discord : {c.discord.status}",
            f"{ok(c.notifs.status == 'ok')} Notifications Windows : {c.notifs.status}",
            f"{ok(c.volume.level is not None)} Audio : {c.volume.device or '—'}",
            f"{ok(c.vpn.ts and c.vpn.ts['running'])} Tailscale : "
            + ((c.vpn.ts or {}).get("state") or ("non installé" if not c.vpn.installed else "—")),
        ]
        self.sources.config(text="\n".join(lines))


if __name__ == "__main__":
    ConfigApp().mainloop()
