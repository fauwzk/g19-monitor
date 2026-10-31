"""Utilitaire de configuration du moniteur G19 (double-clic pour l'ouvrir), en Qt (PySide6).

Les réglages enregistrés sont appliqués à chaud par l'appli, sans la relancer. Seuls les champs
modifiés ici sont enregistrés ; ceux changés ailleurs (menu du G19) sont repris dans la fenêtre.
"""
import os
import subprocess
import sys
import threading
import time
import urllib.error
import webbrowser
from datetime import datetime
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(APP_DIR))
os.chdir(APP_DIR)

from PIL import Image  # noqa: E402
from PySide6.QtCore import QObject, QSize, Qt, QTimer, Signal  # noqa: E402
from PySide6.QtGui import QFont, QIcon  # noqa: E402
from PySide6.QtWidgets import (QAbstractItemView, QApplication, QButtonGroup, QColorDialog,  # noqa: E402
                               QFileDialog, QFrame, QGridLayout, QHBoxLayout, QHeaderView,
                               QLabel, QListWidget, QListWidgetItem, QMainWindow, QMessageBox,
                               QPushButton, QRadioButton, QScrollArea, QStackedWidget,
                               QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget)

import install_hooks  # noqa: E402
import install_startup  # noqa: E402
from g19 import (afterburner, backup, config, fuel, instance, night, remote, rtss, screen,  # noqa: E402
                 settings, steam_live, version, volume)
from g19 import discord as discord_rpc  # noqa: E402
from g19.alerts import DEFAULT_THRESHOLDS, RULES  # noqa: E402
from g19.claude_status import read_sessions  # noqa: E402
from g19.fans import LABELS as FAN_LABELS  # noqa: E402
from g19.launcher import launch  # noqa: E402
from g19.qtkit import (Card, Swatch, Toggle, bind_combo, bind_slider, bind_spin, bind_swatch,  # noqa: E402
                       bind_text, bind_toggle, combo, glyph_icon, hbox, label, line_edit,
                       palette,
                       pil_to_pixmap, slider, spin, stylesheet, title_bar, Field)
from g19.anim import SPEED_LABELS as ANIM_SPEEDS, STYLES as ANIM_STYLES  # noqa: E402
from g19.coverflow import STYLES as COVER_STYLES  # noqa: E402
from g19.render import THEME_LABELS, render, theme_of  # noqa: E402
from g19.tray import make_icon  # noqa: E402
from g19.weather import geocode  # noqa: E402

TITLES = settings.PAGE_TITLES
PREVIEW_SCALE = 1.4
LIVE = "live"
GAME_PAGES = [("", "Ne rien changer"), ("gpu", "GPU"), ("games", "Jeux")]
NIGHT_THEMES = [("", "Inchangé")] + [(k, v) for k, v in THEME_LABELS.items()
                                     if k in ("dark", "g19", "light", "g15", "neon", "dynamic",
                                              "red", "contrast", "glacier", "braise", "terminal",
                                              "hud", "analog", "paper", "paper_dark")]
FUEL_MAIN = [("", "Automatique")] + [(f, f) for f in ("Gazole", "E10", "SP95", "SP98", "E85",
                                                       "GPLc")]
AUDIO_KEEP = "inchangé"
AUDIO_KEEP_IN = "micro inchangé"
PORTAL = "https://discord.com/developers/applications"
# rétroéclairage : (case, libellé, nombre de clignotements, couleur, test)
BACKLIGHT_ROWS = [
    ("backlight_alerts", "Clignote pendant une alerte", None, "color_alert", None),
    ("backlight_waiting", "Pulse quand Claude attend ta réponse", None, "color_waiting", "pulse"),
    ("backlight_working", "Couleur fixe quand Claude travaille", None, "color_working", None),
    ("backlight_done", "Clignote quand Claude a fini", "blinks_done", "color_done", "done"),
    ("backlight_discord", "Clignote à chaque message Discord", "blinks_discord", "color_discord",
     "discord"),
    ("backlight_notifs", "Clignote à chaque notification Windows", "blinks_notifs",
     "color_notif", "notif"),
    (None, "WhatsApp : sa propre couleur", None, "color_whatsapp", "whatsapp"),
    (None, "Snapchat : sa propre couleur", None, "color_snap", "snap"),
]
BLINK_OF = {"done": "blinks_done", "discord": "blinks_discord"}
# touches de l'ordinateur → touches du G19 (quand l'aperçu a le focus)
KEYS = {Qt.Key_Left: "left", Qt.Key_Right: "right", Qt.Key_Up: "up", Qt.Key_Down: "down",
        Qt.Key_Return: "ok", Qt.Key_Enter: "ok", Qt.Key_Space: "ok", Qt.Key_Escape: "cancel",
        Qt.Key_Backspace: "cancel", Qt.Key_M: "menu"}
# page → (icône Segoe Fluent Icons, phrase sous le titre)
PAGE_INFO = {
    "Pages": ("\uE8A9", "Ce que le G19 affiche, dans quel ordre, et au démarrage."),
    "Apparence": ("\uE790", "Thème, image de l'écran et mode nuit."),
    "Bandeaux": ("\uE8BD", "Les messages qui glissent en bas de l'écran du G19."),
    "Clavier et alertes": ("\uE765", "Le rétroéclairage du clavier comme voyant, et les "
                                      "seuils d'alerte."),
    "Audio": ("\uE7F5", "Profils audio : casque, haut-parleurs… à changer d'un geste."),
    "Raccourcis": ("\uE71B", "Les applis à ouvrir depuis le menu du G19."),
    "Services": ("\uE774", "Météo, réseau, Home Assistant, Discord et Steam."),
    "Système": ("\uE713", "L'appli, le démarrage, les ventilateurs et la sauvegarde."),
}


class Bridge(QObject):
    """Rappelle une fonction dans le fil de l'interface (depuis un fil de travail)."""
    call = Signal(object)


class Preview(QLabel):
    """Aperçu de l'écran du G19 ; clic puis flèches / Entrée / Échap / M pour le piloter."""

    def __init__(self, press):
        super().__init__()
        self.press = press
        self.setFocusPolicy(Qt.StrongFocus)
        self.setAlignment(Qt.AlignCenter)
        self.setFixedSize(int(320 * PREVIEW_SCALE), int(240 * PREVIEW_SCALE))
        self.setText("chargement…")
        self.setObjectName("muted")

    def mousePressEvent(self, e):
        self.setFocus()

    def keyPressEvent(self, e):
        b = KEYS.get(e.key())
        if b:
            self.press(b)
        else:
            super().keyPressEvent(e)


class ConfigApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("G19 Monitor — Configuration")
        self.setWindowIcon(QIcon(pil_to_pixmap(make_icon())))
        self.s = settings.load()
        self.theme_name = theme_of(self.s)
        self.fields = {}                  # réglage → Field
        self.toggles = []                 # interrupteurs à recolorer avec le thème
        self.ctx = self.media = None
        self._last_sample = self._last_mirror_req = self._update_at = 0.0
        self.bridge = Bridge()
        self.bridge.call.connect(lambda fn: fn())

        root = QWidget()
        root.setObjectName("root")
        self.setCentralWidget(root)
        outer = QVBoxLayout(root)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        outer.addWidget(self._top_bar())

        body = QHBoxLayout()
        body.setSpacing(0)
        outer.addLayout(body, 1)
        side = QFrame()
        side.setObjectName("side")
        side.setFixedWidth(206)
        sl = QVBoxLayout(side)
        sl.setContentsMargins(0, 12, 0, 12)
        self.nav = QListWidget()
        self.nav.setFont(QFont("Segoe UI", 10))
        self.nav.setUniformItemSizes(True)       # toutes les entrées à la même hauteur
        self.nav.setIconSize(QSize(18, 18))
        self.nav.setFocusPolicy(Qt.NoFocus)
        sl.addWidget(self.nav)
        body.addWidget(side)
        self.stack = QStackedWidget()
        body.addWidget(self.stack, 1)
        body.addWidget(self._preview_panel())
        self.nav.currentRowChanged.connect(self.stack.setCurrentIndex)

        for title, builders in (
                ("Pages", (self._tab_pages,)),
                ("Apparence", (self._tab_display, self._tab_screen, self._tab_night)),
                ("Bandeaux", (self._tab_toasts,)),
                ("Clavier et alertes", (self._tab_alerts,)),
                ("Audio", (self._tab_audio,)),
                ("Raccourcis", (self._tab_shortcuts,)),
                ("Services", (self._tab_weather, self._tab_fuel, self._tab_discord,
                              self._tab_steam)),
                ("Système", (self._tab_system,))):
            lay = self._page(title)
            for build in builders:
                build(lay)
            lay.addStretch(1)
        self.nav.setCurrentRow(0)
        outer.addWidget(self._bottom_bar())

        self.apply_theme(self.theme_name)
        self._base = self.collect()
        self.save_timer = QTimer(self)
        self.save_timer.setSingleShot(True)
        self.save_timer.timeout.connect(self.save)
        self._wire(self.stack)
        self._watch = settings.Watcher()
        threading.Thread(target=self._load_ctx, daemon=True).start()
        self.resize(1360, 860)
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._tick)
        self.timer.start(100)

    # --- cadre ---

    def _top_bar(self):
        top = QFrame()
        top.setObjectName("top")
        lay = QHBoxLayout(top)
        lay.setContentsMargins(20, 12, 20, 12)
        lay.setSpacing(12)
        icon = QLabel()
        icon.setPixmap(pil_to_pixmap(make_icon().resize((34, 34), Image.LANCZOS)))
        lay.addWidget(icon)
        titles = QVBoxLayout()
        titles.setSpacing(0)
        titles.addWidget(label("G19 Monitor", "brand"))
        titles.addWidget(label(f"configuration · version {version.label()}", "brandSub"))
        lay.addLayout(titles)
        lay.addSpacing(10)
        self.state_pill = label("", "pillOff")
        lay.addWidget(self.state_pill, 0, Qt.AlignVCenter)
        lay.addStretch(1)
        self.update_label = label("", "muted")
        lay.addWidget(self.update_label)
        b = QPushButton("Vérifier les mises à jour")
        b.clicked.connect(self._check_update)
        lay.addWidget(b)
        return top

    def _bottom_bar(self):
        bar = QFrame()
        bar.setObjectName("bottom")
        lay = QHBoxLayout(bar)
        lay.setContentsMargins(20, 10, 20, 10)
        self.status = label("", "status")
        lay.addWidget(self.status, 1)
        lay.addWidget(label("Les réglages s'appliquent tout de suite.", "hint"))
        close = QPushButton("Fermer")
        close.clicked.connect(self.close)
        lay.addWidget(close)
        return bar

    def _preview_panel(self):
        wrap = QWidget()
        wrap.setFixedWidth(int(320 * PREVIEW_SCALE) + 56)
        lay = QVBoxLayout(wrap)
        lay.setContentsMargins(8, 20, 20, 20)
        box = QFrame()
        box.setObjectName("previewBox")
        bl = QVBoxLayout(box)
        bl.setContentsMargins(14, 12, 14, 14)
        head = QHBoxLayout()
        head.addWidget(label("APERÇU", "section"))
        head.addStretch(1)
        self.preview_page = combo([(LIVE, "● G19 en direct")] + list(TITLES.items()), 170)
        self.preview_page.setCurrentIndex(0 if instance.is_running() else
                                          self.preview_page.findData(self.s["pages"][0]))
        head.addWidget(self.preview_page)
        bl.addLayout(head)
        bl.addSpacing(8)
        frame = QFrame()
        frame.setObjectName("previewFrame")
        fl = QVBoxLayout(frame)
        fl.setContentsMargins(2, 2, 2, 2)
        self.preview = Preview(self._press)
        fl.addWidget(self.preview)
        bl.addWidget(frame, 0, Qt.AlignHCenter)
        bl.addSpacing(12)
        bl.addWidget(self._keypad())
        self.pad_hint = label("", "hint")
        self.pad_hint.setAlignment(Qt.AlignCenter)
        bl.addWidget(self.pad_hint)
        lay.addWidget(box)
        lay.addStretch(1)
        return wrap

    def _keypad(self):
        """Touches du G19 : Menu et Annuler à gauche, croix et OK à droite."""
        w = QWidget()
        lay = QHBoxLayout(w)
        lay.setContentsMargins(0, 0, 0, 0)
        self._pad_buttons = []

        def key(text, button, width=None):
            b = QPushButton(text)
            b.setObjectName("key")
            if width:
                b.setFixedWidth(width)
            b.clicked.connect(lambda: self._press(button))
            self._pad_buttons.append(b)
            return b

        left = QVBoxLayout()
        left.addWidget(key("Menu", "menu", 92))
        left.addWidget(key("Annuler", "cancel", 92))
        left.addStretch(1)
        lay.addLayout(left)
        lay.addStretch(1)
        cross = QGridLayout()
        cross.setSpacing(4)
        cross.addWidget(key("▲", "up"), 0, 1)
        cross.addWidget(key("◄", "left"), 1, 0)
        cross.addWidget(key("OK", "ok"), 1, 1)
        cross.addWidget(key("►", "right"), 1, 2)
        cross.addWidget(key("▼", "down"), 2, 1)
        lay.addLayout(cross)
        return w

    def _page(self, title):
        """Nouvelle page de réglages (titre, phrase d'aide) ; renvoie son layout."""
        icon, hint = PAGE_INFO.get(title, ("", ""))
        item = QListWidgetItem(title)
        item.setData(Qt.UserRole, icon)          # icône dessinée selon le thème
        item.setSizeHint(QSize(0, 40))
        self.nav.addItem(item)
        page = QWidget()
        lay = QVBoxLayout(page)
        lay.setContentsMargins(28, 22, 18, 22)
        lay.setSpacing(14)
        lay.addWidget(label(title, "pageTitle"))
        if hint:
            lay.addWidget(label(hint, "pageHint", wrap=True))
        lay.addSpacing(4)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setWidget(page)
        self.stack.addWidget(scroll)
        return lay

    def _card(self, lay, title=None):
        card = Card(title)
        lay.addWidget(card)
        return card

    # --- champs liés aux réglages ---

    def toggle(self, key, card, text, hint=None):
        t = Toggle(bool(self.s.get(key)))
        self.toggles.append(t)
        card.row(text, t, hint)
        self.fields[key] = bind_toggle(t)
        return t

    def spin(self, key, card, text, lo, hi, step=1, suffix="", hint=None):
        w = spin(lo, hi, step, suffix)
        w.setValue(int(self.s.get(key) or lo))
        card.row(text, w, hint)
        self.fields[key] = bind_spin(w)
        return w

    def slider(self, key, card, text, lo, hi, step, fmt="{} %", hint=None, value=None):
        box, s = slider(lo, hi, step, fmt)
        s.setValue(int(self.s.get(key) if value is None else value))
        card.row(text, box, hint)
        self.fields[key] = bind_slider(s)
        return s

    def choice(self, key, card, text, items, hint=None, width=200, value=None):
        c = combo(items, width)
        f = bind_combo(c)
        f.set(self.s.get(key) if value is None else value)
        card.row(text, c, hint)
        self.fields[key] = f
        return c

    def text(self, key, card, text, width=240, hint=None, extra=None):
        e = line_edit(self.s.get(key) or "", width)
        card.row(text, hbox(e, extra) if extra else e, hint)
        self.fields[key] = bind_text(e)
        return e

    def button(self, text, fn, accent=False):
        b = QPushButton(text)
        if accent:
            b.setObjectName("accent")
        b.clicked.connect(fn)
        return b

    def later(self, fn):
        """Depuis un fil de travail : exécute fn dans le fil de l'interface."""
        self.bridge.call.emit(fn)

    def work(self, job, done):
        """job() dans un fil à part, puis done(résultat) dans l'interface."""
        def run():
            try:
                result = job()
            except Exception as e:      # noqa: BLE001 — affiché tel quel
                result = e
            self.later(lambda: done(result))
        threading.Thread(target=run, daemon=True).start()

    # --- onglets ---

    def _tab_pages(self, lay):
        card = self._card(lay, "Pages affichées")
        self.pages = QListWidget()
        self.pages.setDragDropMode(QAbstractItemView.InternalMove)
        self.pages.setMinimumHeight(330)
        self.pages.setUniformItemSizes(True)
        enabled = self.s["pages"]
        for pid in enabled + [p for p in TITLES if p not in enabled]:
            it = QListWidgetItem(TITLES[pid])
            it.setData(Qt.UserRole, pid)
            it.setFlags(it.flags() | Qt.ItemIsUserCheckable | Qt.ItemIsDragEnabled)
            it.setCheckState(Qt.Checked if pid in enabled else Qt.Unchecked)
            it.setSizeHint(QSize(0, 30))
            self.pages.addItem(it)
        self.pages.currentItemChanged.connect(
            lambda it, _old: it and self.preview_page.setCurrentIndex(
                self.preview_page.findData(it.data(Qt.UserRole))))
        card.widget(self.pages)
        card.note("Coche les pages à afficher ; glisse-les pour changer leur ordre (◄ ► sur le "
                  "G19). Cliquer une page la montre dans l'aperçu.")
        self.fields["pages"] = Field(self._pages_get, lambda v: None)

        card = self._card(lay, "Liste des écrans (touche Menu)")
        self.choice("screen_list_style", card, "Présentation",
                    [(k, v.capitalize()) for k, v in COVER_STYLES.items()],
                    "Coverflow en perspective, cartes à plat, grille de miniatures, ou liste "
                    "avec l'aperçu de l'écran choisi.", 180)

        card = self._card(lay, "Au démarrage")
        self.remember = QRadioButton("Rouvrir sur la dernière page affichée")
        fixed = QRadioButton("Toujours ouvrir sur :")
        group = QButtonGroup(self)
        group.addButton(self.remember)
        group.addButton(fixed)
        (self.remember if self.s["remember_page"] else fixed).setChecked(True)
        card.widget(self.remember)
        start = combo(list(TITLES.items()), 170)
        bind_combo(start).set(self.s["start_page"])
        card.widget(hbox(fixed, start, stretch=True))
        self.fields["remember_page"] = Field(self.remember.isChecked,
                                             lambda v: (self.remember if v else fixed).setChecked(True))
        self.fields["start_page"] = bind_combo(start, "system")

        card = self._card(lay, "Au lancement d'un jeu")
        self.choice("game_page", card, "Afficher la page", GAME_PAGES, width=170,
                    hint="Retour à la page d'avant une fois la partie finie.")
        bl = line_edit(", ".join(self.s.get("game_blacklist") or []), 260,
                       placeholder="obs, …")
        card.row("Jamais traités comme des jeux", bl,
                 "Début du nom d'exécutable, séparés par des virgules (« obs » couvre obs64, "
                 "obs32…). Ni écran de jeu, ni récapitulatif. Aussi depuis le menu du G19 "
                 "pendant une partie : « Pas un jeu ».")
        self.fields["game_blacklist"] = Field(
            lambda: [a.strip() for a in bl.text().split(",") if a.strip()],
            lambda v: bl.setText(", ".join(v or [])))
        self.measured = combo([], 200)
        card.row("Applis mesurées en ce moment", hbox(
            self.measured, self.button("Exclure", lambda: self._exclude_game(bl)),
            self.button("Actualiser", self._load_measured)),
            "Ce que RivaTuner voit tourner (jeux et applis 3D) : choisis-en une à exclure.")
        self._load_measured()

    def _load_measured(self):
        try:
            names = sorted({a["name"] for a in rtss.read_apps() or []}, key=str.lower)
        except Exception:
            names = []
        self.measured.clear()
        for n in names or ["(aucune)"]:
            self.measured.addItem(n, n if names else None)

    def _exclude_game(self, bl):
        name = self.measured.currentData()
        if not name:
            return
        key = rtss.blacklist_key(name)
        items = [a.strip() for a in bl.text().split(",") if a.strip()]
        if key not in items:
            bl.setText(", ".join(items + [key]))
            self.changed()
            self._flash(f"{name} : plus traité comme un jeu.")

    def _pages_get(self):
        out = []
        for i in range(self.pages.count()):
            it = self.pages.item(i)
            if it.checkState() == Qt.Checked:
                out.append(it.data(Qt.UserRole))
        return out or ["system"]

    def _tab_display(self, lay):
        card = self._card(lay, "Thème")
        c = self.choice("theme", card, "Thème", list(THEME_LABELS.items()),
                        "Celui de l'écran du G19 ; cette fenêtre le suit.", 220,
                        value=theme_of(self.s))
        c.currentIndexChanged.connect(lambda _i: self.apply_theme(c.currentData()))
        self.toggle("wallpaper_bg", card, "Fond d'écran Windows derrière les pages",
                    "Flouté, avec des panneaux translucides ; suit le diaporama. Toujours actif "
                    "avec le thème Aero.")
        self.slider("wallpaper_dim", card, "Assombrissement du fond", 0, 90, 5,
                    hint="Plus haut : texte plus lisible, fond plus discret.")
        self.toggle("animations", card, "Animations",
                    "Entre les pages (◄ ►) ; menus et écrans apparaissent en fondu.")
        style = combo([(k, v[0].capitalize()) for k, v in ANIM_STYLES.items()], 130)
        bind_combo(style).set(self.s.get("animation_style", "slide"))
        speed = combo([(k, v.capitalize()) for k, v in ANIM_SPEEDS.items()], 110)
        bind_combo(speed).set(self.s.get("animation_speed", "normal"))
        card.row("Style entre les pages", hbox(style, speed),
                 "Glisser, fondu, zoom, volet, cube ou stores, et la vitesse.")
        card.row("Voir l'animation", self.button("Essayer sur le G19", self._try_anim),
                 "Passe le G19 à la page suivante avec l'animation choisie.")
        self.fields["animation_style"] = bind_combo(style, "slide")
        self.fields["animation_speed"] = bind_combo(speed, "normal")
        self.spin("fps", card, "Images par seconde", 2, 60,
                  hint="Jusqu'à 60. Une page fixe ne coûte presque rien ; la fluidité réelle "
                       "s'affiche dans le menu du G19.")
        card = self._card(lay, "Jauges et encarts")
        self.spin("gpu_power_max", card, "Puissance max. du GPU", 100, 700, 5, "W",
                  "Échelle de la jauge Puissance de l'écran GPU.")
        self.spin("claude_strip_seconds", card, "Encart Claude masqué après", 0, 600, 5, "s",
                  "Après la fin du dernier agent, l'encart s'efface (0 = jamais).")

    def _tab_screen(self, lay):
        card = self._card(lay, "Image")
        self.slider("screen_brightness", card, "Luminosité", 50, 150, 5)
        self.slider("screen_contrast", card, "Contraste", 50, 150, 5)
        self.slider("screen_gamma", card, "Tons sombres (gamma)", 60, 160, 5,
                    hint="Au-dessus de 100 %, les gris foncés et textes estompés ressortent.")
        self.slider("screen_saturation", card, "Saturation", 0, 200, 10, hint="0 % : noir et blanc.")
        self.toggle("screen_sharpen", card, "Netteté renforcée", "Contours des petits textes plus nets.")
        self.toggle("screen_dither", card, "Dégradés lissés (tramage)",
                    "L'écran du G19 n'a que 65 000 couleurs : sans tramage, les fonds flous "
                    "(pochette, fond d'écran) se découpent en bandes.")
        card = self._card(lay, "Réglage à l'œil")
        card.row("Mire de réglage", hbox(self.button("Afficher la mire sur le G19",
                                                     self._show_pattern, True),
                                         self.button("Valeurs d'origine", self._reset_screen)),
                 "Marches de gris, couleurs et textes de 8 à 16 px pendant 20 s. Enregistre pour "
                 "voir l'effet de tes réglages.")

    def _try_anim(self):
        if not instance.is_running():
            return self._flash("L'appli doit tourner pour essayer l'animation.")
        self.save(quiet=True)          # le style choisi d'abord, puis la page suivante
        config.save("flash_test.json", {"kind": "anim", "at": time.time()})
        self._flash("Page suivante sur le G19, avec l'animation choisie.")

    def _show_pattern(self):
        if not instance.is_running():
            return self._flash("L'appli doit tourner pour afficher la mire.")
        config.save("flash_test.json", {"kind": "pattern", "at": time.time()})
        self._flash("Mire affichée sur le G19 pendant 20 s (une touche pour la fermer).")

    def _reset_screen(self):
        for k in ("screen_brightness", "screen_contrast", "screen_gamma", "screen_saturation"):
            self.fields[k].set(100)
        self.fields["screen_sharpen"].set(False)

    def _tab_toasts(self, lay):
        card = self._card(lay, "Messages")
        self.toggle("discord_toasts", card, "Messages Discord",
                    "Avec le nom du groupe ou du salon ; OK ouvre la conversation dans Discord.")
        self.toggle("win_toasts", card, "Notifications Windows")
        e = line_edit(", ".join(self.s["notif_ignore"]), 260, placeholder="Sécurité Windows, …")
        card.row("Applis ignorées", e, "Séparées par des virgules. Les notifs Discord sont "
                                       "masquées d'office quand l'écran Discord est connecté.")
        self.fields["notif_ignore"] = Field(
            lambda: [a.strip() for a in e.text().split(",") if a.strip()],
            lambda v: e.setText(", ".join(v or [])))
        self.spin("toast_seconds", card, "Durée d'affichage", 2, 30, suffix="s",
                  hint="Pendant qu'un bandeau est là : OK ouvre sa page, Annuler le ferme.")
        card = self._card(lay, "Événements")
        for key, text, hint in (
                ("media_toasts", "Changement de musique / média", None),
                ("device_toasts", "Périphérique connecté ou retiré",
                 "USB, Bluetooth et audio, avec la batterie quand il en a une."),
                ("steam_toasts", "Ami Steam connecté", "Avec sa photo de profil."),
                ("voice_toasts", "Arrivée / départ dans l'appel Discord", None),
                ("stream_toasts", "Connexion en streaming à ce PC",
                 "Moonlight (via Sunshine) ou Parsec, voyant rouge tant que ça dure."),
                ("docker_toasts", "Conteneur Docker en panne",
                 "Arrêté en erreur, ou qui redémarre en boucle (3 fois en 5 min)."),
                ("rain_toasts", "Pluie dans peu de temps",
                 "« Pluie dans ~30 min » quand il ne pleut pas encore (prévision au quart "
                 "d'heure)."),
                ("claude_reminders", "Rappel : Claude attend ta réponse",
                 "Après 10 min, puis toutes les 10 min : bandeau et deux clignotements "
                 "discrets. OK ouvre la session."),
                ("fuel_toasts", "Carburant en rupture ou de retour", None),
                ("page_toasts", "Page de nouveau disponible",
                 "Discord et Docker sont masquées tant que l'appli est fermée."),
                ("driver_toasts", "Nouveau pilote graphique AMD",
                 "Rappel une fois par jour tant qu'il n'est pas installé.")):
            self.toggle(key, card, text, hint)
        card = self._card(lay, "PC au repos")
        self.toggle("idle_screen", card, "Horloge quand le PC est verrouillé ou inactif",
                    "Avec la météo et ce qui est arrivé entre-temps. Pas pendant un jeu ni une "
                    "vidéo.")
        self.spin("idle_minutes", card, "Inactif après", 1, 120, suffix="min")
        self.toggle("away_summary", card, "Résumé « pendant ton absence » au retour")
        self.spin("away_min_minutes", card, "Absence minimale", 0, 240, suffix="min")

    def _tab_night(self, lay):
        card = self._card(lay, "Mode nuit")
        self.toggle("night_mode", card, "Activer")
        hours = [(h, h) for h in night.HOURS]
        start, end = combo(hours, 90), combo(hours, 90)
        bind_combo(start).set(self.s["night_start"])
        bind_combo(end).set(self.s["night_end"])
        card.row("Plage horaire", hbox(start, label("→", "muted"), end))
        self.fields["night_start"] = bind_combo(start, "23:00")
        self.fields["night_end"] = bind_combo(end, "07:00")
        card = self._card(lay, "Pendant la nuit")
        self.spin("night_dim", card, "Luminosité de l'écran", 10, 100, 10, "%")
        self.choice("night_theme", card, "Thème", NIGHT_THEMES, "« Inchangé » garde celui du jour.")
        self.toggle("night_quiet", card, "Clavier discret", "Seules les alertes font clignoter.")

    def _tab_weather(self, lay):
        card = self._card(lay, "Météo")
        self.city_state = label("", "hint")
        self.text("weather_city", card, "Ville", 200,
                  "Vide : la position de Windows (Wi-Fi, précise), sinon d'après l'adresse IP.",
                  extra=self.button("Vérifier", self._check_city))
        card.widget(self.city_state)
        card = self._card(lay, "Réseau")
        self.text("ping_target", card, "Cible du ping", 200,
                  "Un ping par seconde pour l'écran Réseau ; alertes en jeu sur un pic de "
                  "latence ou des pertes.")

    def _check_city(self):
        city = self.fields["weather_city"].get()
        if not city:
            return self.city_state.setText("Vide : position de Windows, sinon d'après l'IP.")
        self.city_state.setText("Recherche…")

        def done(p):
            if isinstance(p, Exception):
                self.city_state.setText("✘ pas de connexion")
            else:
                self.city_state.setText(f"✔ {p['name']}, {p['admin']}, {p['country']}" if p
                                        else "✘ ville introuvable")
        self.work(lambda: geocode(city), done)

    def _tab_alerts(self, lay):
        card = self._card(lay, "Alertes")
        self.toggle("alerts_on", card, "Alertes actives", "Bandeau, cadre rouge et rétroéclairage.")
        values = {**DEFAULT_THRESHOLDS, **self.s["alerts"]}
        spins = {}
        for key, (text, unit) in RULES.items():
            spins[key] = s = spin(0, 120, 1, unit)
            s.setValue(int(values[key]))
            card.row(text, s)
        card.note("0 = désactivé.")
        self.fields["alerts"] = Field(lambda: {k: s.value() for k, s in spins.items()},
                                      lambda v: [spins[k].setValue(int(x)) for k, x in v.items()
                                                 if k in spins])

        card = self._card(lay, "Rétroéclairage du G19 comme voyant")
        self.toggle("backlight", card, "Activer", "Sinon l'éclairage de LGS n'est jamais modifié.")
        for key, text, blink, color, test in BACKLIGHT_ROWS:
            parts = []
            if blink:
                n = spin(1, 10, 1, "fois", 70)
                n.setValue(int(self.s[blink]))
                self.fields[blink] = bind_spin(n)
                parts.append(n)
            if test:
                parts.append(self.button("Tester", lambda _=False, t=test, c=color:
                                         self._test_backlight(t, c)))
            sw = Swatch(self.s.get(color, ""))
            sw.clicked.connect(lambda _=False, w=sw: self._pick_color(w, "Couleur de l'effet"))
            self.fields[color] = bind_swatch(sw)
            parts.append(sw)
            if key:
                t = Toggle(bool(self.s[key]))
                self.toggles.append(t)
                self.fields[key] = bind_toggle(t)
                parts.append(t)
            card.row(text if key else f"      {text}", hbox(*parts, spacing=8))
        self.slider("blink_ms", card, "Vitesse de clignotement", *settings.BLINK_RANGE, 5,
                    "{} ms", "À gauche rapide, à droite lent.",
                    value=settings.blink_ms(self.s["blink_ms"]))
        self.slider("pulse_ms", card, "Pulsation « Claude attend »", *settings.PULSE_RANGE, 5,
                    "{} ms", value=settings.pulse_ms(self.s["pulse_ms"], 300))
        base = Swatch(self.s["backlight_base"])
        base.clicked.connect(lambda: self._pick_color(base, "Couleur du clavier au repos"))
        card.row("Couleur au repos", hbox(base, self.button("Restaurer", lambda: base.set(""))),
                 "Après un effet. Vide : l'éclairage enregistré dans LGS.")
        self.fields["backlight_base"] = bind_swatch(base)
        card.note("Dans Logitech Gaming Software, « Autoriser les jeux à contrôler l'éclairage » "
                  "doit être coché.")

        card = self._card(lay, "Système et jeux")
        self.toggle("sys_alerts", card, "Redémarrage en attente ou disque presque plein")
        self.spin("disk_free_gb", card, "Disque presque plein sous", 1, 200, suffix="Go")
        self.toggle("game_recap", card, "Récapitulatif à la fin d'une partie")

    def _test_backlight(self, test, color_key):
        if not instance.is_running():
            return self._flash("L'appli doit tourner pour piloter le clavier.")
        if test == "pulse":
            config.save("flash_test.json", {"kind": "waiting", "at": time.time(),
                                            "ms": self.fields["pulse_ms"].get(),
                                            "color": self.fields[color_key].get()})
            return self._flash("Pulsation envoyée au clavier pendant 6 s.")
        if not self.fields["backlight"].get():
            return self._flash("Active d'abord le rétroéclairage.")
        blink = self.fields[BLINK_OF.get(test, "blinks_notifs")].get()
        config.save("flash_test.json", {"kind": test, "at": time.time(), "count": blink,
                                        "ms": self.fields["blink_ms"].get(),
                                        "color": self.fields[color_key].get()})
        self._flash("Test envoyé au clavier…")

    def _pick_color(self, swatch, title):
        from PySide6.QtGui import QColor
        c = QColorDialog.getColor(QColor(swatch.color or "#ffffff"), self, title)
        if c.isValid():
            swatch.set(c.name().lower())

    def _tab_shortcuts(self, lay):
        card = self._card(lay, "Applis du menu du G19")
        self.sc_table = self._table(["Nom", "Cible"])
        card.widget(self.sc_table)
        self._shortcuts = [dict(sc) for sc in self.s["shortcuts"]]
        self.sc_name, self.sc_target, self.sc_args = line_edit(), line_edit(), line_edit()
        card.row("Nom", self.sc_name)
        card.row("Cible", hbox(self.sc_target, self.button("Parcourir…", self._browse_exe)),
                 "Un .exe, un dossier, une adresse web ou un lien d'appli (discord://, "
                 "steam://rungameid/730…).")
        card.row("Arguments", self.sc_args)
        card.widget(hbox(self.button("Ajouter", self._add_shortcut, True),
                         self.button("Modifier", self._edit_shortcut),
                         self.button("Supprimer", self._del_shortcut),
                         self.button("▲", lambda: self._move_row(self._shortcuts, self.sc_table, -1,
                                                                 self._refresh_shortcuts)),
                         self.button("▼", lambda: self._move_row(self._shortcuts, self.sc_table, 1,
                                                                 self._refresh_shortcuts)),
                         self.button("Tester", self._test_shortcut), stretch=True))
        card.note("Le menu propose aussi toujours l'appli liée à la page affichée (Discord, "
                  "lecteur média, dernier jeu, Afterburner…).")
        self.sc_table.itemSelectionChanged.connect(self._on_shortcut)
        self._refresh_shortcuts()
        self.fields["shortcuts"] = Field(lambda: self._shortcuts, lambda v: None)

    def _table(self, headers, height=210):
        t = QTableWidget(0, len(headers))
        t.setHorizontalHeaderLabels(headers)
        t.verticalHeader().hide()
        t.setSelectionBehavior(QAbstractItemView.SelectRows)
        t.setSelectionMode(QAbstractItemView.SingleSelection)
        t.setEditTriggers(QAbstractItemView.NoEditTriggers)
        t.setShowGrid(False)
        t.setAlternatingRowColors(True)
        t.horizontalHeader().setStretchLastSection(True)
        t.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        t.setMinimumHeight(height)
        return t

    @staticmethod
    def _fill(table, rows, select=None):
        table.setRowCount(0)
        for r, values in enumerate(rows):
            table.insertRow(r)
            for col, v in enumerate(values):
                table.setItem(r, col, QTableWidgetItem(v))
        if select is not None and 0 <= select < len(rows):
            table.selectRow(select)

    @staticmethod
    def _selected(table):
        rows = table.selectionModel().selectedRows()
        return rows[0].row() if rows else None

    def _move_row(self, items, table, step, refresh):
        i = self._selected(table)
        if i is not None and 0 <= i + step < len(items):
            items[i], items[i + step] = items[i + step], items[i]
            refresh(i + step)

    def _refresh_shortcuts(self, select=None):
        self._fill(self.sc_table, [(sc["name"], sc["target"] + (f" {sc['args']}" if sc.get("args")
                                                                else "")) for sc in self._shortcuts],
                   select)

    def _on_shortcut(self):
        i = self._selected(self.sc_table)
        if i is not None:
            sc = self._shortcuts[i]
            self.sc_name.setText(sc["name"])
            self.sc_target.setText(sc["target"])
            self.sc_args.setText(sc.get("args", ""))

    def _form_shortcut(self):
        name, target = self.sc_name.text().strip(), self.sc_target.text().strip()
        if not name or not target:
            self._flash("Renseigne un nom et une cible.")
            return None
        return {"name": name, "target": target, "args": self.sc_args.text().strip()}

    def _add_shortcut(self):
        sc = self._form_shortcut()
        if sc:
            self._shortcuts.append(sc)
            self._refresh_shortcuts(len(self._shortcuts) - 1)

    def _edit_shortcut(self):
        i, sc = self._selected(self.sc_table), self._form_shortcut()
        if i is not None and sc:
            self._shortcuts[i] = sc
            self._refresh_shortcuts(i)

    def _del_shortcut(self):
        i = self._selected(self.sc_table)
        if i is not None:
            del self._shortcuts[i]
            self._refresh_shortcuts(min(i, len(self._shortcuts) - 1))

    def _test_shortcut(self):
        sc = self._form_shortcut()
        if sc:
            try:
                launch(sc["target"], sc["args"])
            except OSError as e:
                self._flash(f"Impossible d'ouvrir : {e}")

    def _browse_exe(self):
        path, _ = QFileDialog.getOpenFileName(self, "Choisir une appli", "",
                                              "Programmes (*.exe *.lnk);;Tout (*.*)")
        if path:
            self.sc_target.setText(str(Path(path)))
            if not self.sc_name.text().strip():
                self.sc_name.setText(Path(path).stem)

    def _tab_audio(self, lay):
        card = self._card(lay, "Profils audio")
        self.ap_table = self._table(["Profil", "Sortie", "Volume"], 170)
        card.widget(self.ap_table)
        self._audio_profiles = [dict(p) for p in self.s.get("audio_profiles") or []]
        self._devices = ([], [])
        self.ap_name = line_edit(width=220)
        self.ap_out, self.ap_in = combo([], 330), combo([], 330)
        self.ap_vol = combo([(None, AUDIO_KEEP)] + [(v, f"{v} %") for v in range(0, 101, 5)], 120)
        card.row("Nom", self.ap_name)
        card.row("Sortie", self.ap_out)
        card.row("Micro", self.ap_in)
        card.row("Volume", self.ap_vol)
        card.widget(hbox(self.button("Ajouter", self._add_profile, True),
                         self.button("Modifier", self._edit_profile),
                         self.button("Supprimer", self._del_profile),
                         self.button("▲", lambda: self._move_row(self._audio_profiles,
                                                                 self.ap_table, -1,
                                                                 self._refresh_profiles)),
                         self.button("▼", lambda: self._move_row(self._audio_profiles,
                                                                 self.ap_table, 1,
                                                                 self._refresh_profiles)),
                         self.button("Appliquer", self._apply_profile),
                         self.button("Actualiser", self._load_devices), stretch=True))
        self.ap_auto_note = card.note(
            "(auto) : profils détectés tout seuls d'après le nom des sorties, utilisés tant que "
            "tu n'en as pas créé. Modifie-en un, ou ajoutes-en, pour qu'ils deviennent les "
            "tiens (enregistrés tout de suite).")
        card.note("Changer de profil : écran Audio du G19 (OK puis ◄ ►), menu du G19, ou clic "
                  "droit sur l'icône G19 → Profil audio.")
        self.ap_table.itemSelectionChanged.connect(self._on_profile)
        self._refresh_profiles()
        self.fields["audio_profiles"] = Field(lambda: self._audio_profiles, lambda v: None)
        self._load_devices()

    def _load_devices(self):
        def done(devs):
            if isinstance(devs, Exception):
                devs = ([], [])
            self._devices = devs
            keep_out, keep_in = self.ap_out.currentText(), self.ap_in.currentText()
            self.ap_out.clear()
            self.ap_in.clear()
            for _i, n in devs[0]:
                self.ap_out.addItem(n, n)
            self.ap_in.addItem(AUDIO_KEEP_IN, "")
            for _i, n in devs[1]:
                self.ap_in.addItem(n, n)
            self.ap_out.setCurrentText(keep_out)
            if keep_in:
                self.ap_in.setCurrentText(keep_in)
            # aucun profil enregistré : ceux que le G19 utilise tout seul, montrés ici
            self._auto = volume.auto_profiles(devs[0])
            self._refresh_profiles()
        self._auto = []
        self.work(volume.list_devices, done)

    def _shown_profiles(self):
        """Profils enregistrés, sinon les automatiques (casque / haut-parleurs détectés)."""
        return self._audio_profiles or getattr(self, "_auto", [])

    def _adopt_auto(self):
        """Avant une modification : les profils automatiques deviennent des profils à soi."""
        if not self._audio_profiles and getattr(self, "_auto", None):
            self._audio_profiles = [{k: v for k, v in p.items() if k != "auto"}
                                    | {"in": "", "in_id": "", "volume": None} for p in self._auto]

    def _refresh_profiles(self, select=None):
        auto = not self._audio_profiles
        self._fill(self.ap_table, [(p["name"] + ("  (auto)" if auto else ""),
                                    p.get("out") or "—",
                                    "—" if p.get("volume") is None else f"{p['volume']} %")
                                   for p in self._shown_profiles()], select)
        if hasattr(self, "ap_auto_note"):
            self.ap_auto_note.setVisible(auto and bool(self._shown_profiles()))

    def _on_profile(self):
        i = self._selected(self.ap_table)
        if i is None:
            return
        p = self._shown_profiles()[i]
        self.ap_name.setText(p["name"])
        if p.get("out") and self.ap_out.findText(p["out"]) < 0:
            self.ap_out.addItem(p["out"], p["out"])     # périphérique absent pour l'instant
        self.ap_out.setCurrentText(p.get("out") or "")
        self.ap_in.setCurrentText(p.get("in") or AUDIO_KEEP_IN)
        bind_combo(self.ap_vol).set(p.get("volume"))

    def _form_profile(self):
        name, out = self.ap_name.text().strip(), self.ap_out.currentText().strip()
        if not name or not out:
            self._flash("Renseigne un nom et une sortie.")
            return None
        mic = self.ap_in.currentData() or ""

        def dev_id(devs, n):
            return next((i for i, dn in devs if dn == n), "")

        return {"name": name, "out": out, "out_id": dev_id(self._devices[0], out),
                "in": mic, "in_id": dev_id(self._devices[1], mic) if mic else "",
                "volume": self.ap_vol.currentData()}

    def _add_profile(self):
        p = self._form_profile()
        if p:
            self._adopt_auto()
            self._audio_profiles.append(p)
            self._refresh_profiles(len(self._audio_profiles) - 1)

    def _edit_profile(self):
        i, p = self._selected(self.ap_table), self._form_profile()
        if i is not None and p:
            self._adopt_auto()
            self._audio_profiles[i] = p
            self._refresh_profiles(i)

    def _del_profile(self):
        i = self._selected(self.ap_table)
        if i is not None:
            self._adopt_auto()
            del self._audio_profiles[i]
            self._refresh_profiles(min(i, len(self._audio_profiles) - 1))

    def _apply_profile(self):
        p = self._form_profile()
        if not p:
            return

        def job():
            import comtypes
            comtypes.CoInitialize()
            try:
                return volume.apply_profile(p)[1]
            finally:
                comtypes.CoUninitialize()
        self.work(job, lambda r: self._flash(f"Profil « {p['name']} » : "
                                             f"{r if not isinstance(r, Exception) else r}"))

    def _tab_fuel(self, lay):
        card = self._card(lay, "Home Assistant")
        card.note("Les prix viennent de l'intégration « Prix Carburant » de Home Assistant. "
                  "Crée un jeton dans ton profil → Sécurité → Jetons d'accès longue durée, puis "
                  "colle l'adresse et le jeton ici. Le jeton reste sur ce PC et n'est envoyé "
                  "qu'à cette adresse.")
        url, token = fuel.load_ha()
        self.ha_url = line_edit(url, 300, placeholder="https://homeassistant.local:8123")
        self.ha_token = line_edit(token, 300, secret=True)
        card.row("Adresse", self.ha_url)
        card.row("Jeton", self.ha_token)
        card.widget(hbox(self.button("Enregistrer et tester", self._save_ha, True),
                         self.button("Ouvrir la page des jetons", self._open_ha_tokens),
                         stretch=True))
        self.ha_state = card.widget(label("", "hint", wrap=True))
        card = self._card(lay, "Carburant")
        self.choice("fuel_main", card, "Mis en avant", FUEL_MAIN,
                    "Carburant dont le prix le plus bas s'affiche en grand (automatique : celui "
                    "que le plus de stations vendent).", 160)

    def _open_ha_tokens(self):
        url = self.ha_url.text().strip().rstrip("/")
        if url:
            webbrowser.open(f"{url}/profile/security")
        else:
            self.ha_state.setText("Renseigne d'abord l'adresse de Home Assistant.")

    def _save_ha(self):
        url, token = self.ha_url.text().strip().rstrip("/"), self.ha_token.text().strip()
        if url and not url.startswith(("http://", "https://")):
            url = "https://" + url
            self.ha_url.setText(url)
        fuel.save_ha(url, token)
        if not (url and token):
            return self.ha_state.setText("Accès oublié." if not (url or token) else
                                         "Il faut l'adresse et le jeton.")
        self.ha_state.setText("Test en cours…")

        def done(r):
            if isinstance(r, urllib.error.HTTPError):
                msg = fuel.http_error_text(r)
                text = msg[0].upper() + msg[1:] + "."
            elif isinstance(r, Exception):
                text = f"Home Assistant injoignable : {r.__class__.__name__}"
            else:
                prices = sum(len(s["fuels"]) for s in r.values())
                text = (f"✔ Connecté : {len(r)} station(s), {prices} prix. La page Carburant se "
                        "met à jour dans la minute." if r else
                        "Connecté, mais aucune station « Prix Carburant » trouvée.")
            self.ha_state.setText(text)
        self.work(lambda: fuel.parse_states(fuel.fetch_states(url, token)), done)

    def _tab_discord(self, lay):
        card = self._card(lay, "Discord")
        card.note("1. Crée une application sur le portail développeur Discord.\n"
                  "2. Onglet OAuth2 : copie le Client ID et le Client Secret.\n"
                  "3. OAuth2 → Redirects : ajoute http://localhost puis Save.\n"
                  "4. Colle-les ici et clique sur « Autoriser » : accepte la fenêtre qui s'ouvre "
                  "dans Discord.")
        cfg = config.load(discord_rpc.CONFIG_FILE, {}) or {}
        self.client_id = line_edit(cfg.get("client_id", ""), 300)
        self.client_secret = line_edit(cfg.get("client_secret", ""), 300, secret=True)
        card.row("Client ID", self.client_id)
        card.row("Client Secret", self.client_secret)
        card.widget(hbox(self.button("Autoriser dans Discord", self._authorize, True),
                         self.button("Oublier l'accès", self._forget),
                         self.button("Ouvrir le portail développeur",
                                     lambda: webbrowser.open(PORTAL)), stretch=True))
        self.discord_state = card.widget(label("", "hint", wrap=True))
        self._refresh_discord_state()

    def _authorize(self):
        cid, secret = self.client_id.text().strip(), self.client_secret.text().strip()
        if not cid or not secret:
            return self.discord_state.setText("Renseigne le Client ID et le Client Secret.")
        self.discord_state.setText("Accepte la demande d'autorisation dans Discord…")

        def done(r):
            if isinstance(r, discord_rpc.RpcError):
                text = f"Échec : {r}"
            elif isinstance(r, Exception):
                text = (f"Échec de l'échange du jeton : {r}\nVérifie le secret et la "
                        f"redirection {discord_rpc.REDIRECT_URI}.")
            else:
                text = f"✔ Autorisé pour {r}. L'écran Discord s'activera dans les 15 s."
            self.discord_state.setText(text)
        self.work(lambda: discord_rpc.authorize(cid, secret), done)

    def _forget(self):
        discord_rpc.forget()
        self._refresh_discord_state()

    def _refresh_discord_state(self):
        cfg = config.load(discord_rpc.CONFIG_FILE, {}) or {}
        if cfg.get("access_token"):
            exp = datetime.fromtimestamp(cfg.get("expires_at", 0)).strftime("%d/%m/%Y")
            self.discord_state.setText(f"✔ Accès autorisé (renouvelé automatiquement, prochain "
                                       f"le {exp}).")
        else:
            self.discord_state.setText("Pas encore autorisé.")

    def _tab_steam(self, lay):
        card = self._card(lay, "Steam")
        card.note("Les téléchargements et mises à jour s'affichent sans rien régler. Pour voir "
                  "tes amis en ligne, il faut ta clé d'API Web Steam : ouvre la page de la clé "
                  "(nom de domaine : localhost), copie-la ici. Elle reste sur ce PC et n'est "
                  "envoyée qu'à Steam. Ta liste d'amis doit être visible.")
        self.steam_key = line_edit(steam_live.load_key(), 300, secret=True)
        card.row("Clé API", self.steam_key)
        card.widget(hbox(self.button("Enregistrer la clé", self._save_steam_key, True),
                         self.button("Oublier la clé", lambda: (self.steam_key.setText(""),
                                                                self._save_steam_key())),
                         self.button("Ouvrir la page de la clé", lambda: webbrowser.open(
                             "https://steamcommunity.com/dev/apikey")), stretch=True))
        self.steam_state = card.widget(label("", "hint", wrap=True))

    def _save_steam_key(self):
        steam_live.save_key(self.steam_key.text())
        self.steam_state.setText("✔ Clé enregistrée : l'écran Steam se met à jour dans la minute."
                                 if self.steam_key.text().strip() else "Clé oubliée.")

    def _tab_system(self, lay):
        card = self._card(lay, "Appli")
        card.row("Moniteur G19", hbox(self.button("Démarrer", lambda: self._control("start")),
                                      self.button("Redémarrer", lambda: self._control("restart")),
                                      self.button("Arrêter", lambda: self._control("stop"))),
                 "Un gardien la relance si elle plante ; Arrêter le coupe aussi.")
        for module, text, hint in (
                (install_startup, "Lancer au démarrage de Windows", None),
                (install_hooks, "Voyant Claude", "Hooks dans ~/.claude/settings.json.")):
            t = Toggle(module.is_installed())
            self.toggles.append(t)
            t.toggled.connect(lambda on, m=module, w=t: self._apply_flag(m, w, on))
            card.row(text, t, hint)

        card = self._card(lay, "Ventilateurs carte mère (via LibreHardwareMonitor)")
        self.choice("fan_profile", card, "Profil", list(FAN_LABELS.items()),
                    "Hors « auto », vitesse fixe (30 % minimum) ; la pompe n'est jamais touchée.",
                    170)
        self.spin("fan_safe_cpu", card, "Retour en auto si CPU ≥", 60, 100, suffix="°C")
        self.spin("fan_safe_gpu", card, "ou hotspot GPU ≥", 60, 100, suffix="°C")
        self.spin("fan_recover_seconds", card, "Retour au profil, refroidi depuis", 10, 900, 10,
                  "s", "Le profil revient seul une fois CPU et GPU 8 °C sous les seuils pendant "
                       "cette durée. Auto aussi à la fermeture de l'appli.")

        card = self._card(lay, "Sources de données")
        self.sources = card.widget(label("…"))
        self.sources.setFont(QFont("Consolas", 9))
        card.widget(hbox(self.button("Journal", lambda: self._open(APP_DIR / "g19.log")),
                         self.button("Données", lambda: self._open(config.DATA_DIR)),
                         self.button("Historique des débits",
                                     lambda: self._open(config.DATA_DIR / "speedtests.csv")),
                         self.button("Dossier de l'appli", lambda: self._open(APP_DIR)),
                         stretch=True))

        card = self._card(lay, "Sauvegarde des réglages")
        self.bk_secrets, self.bk_history = Toggle(True), Toggle(True)
        self.toggles += [self.bk_secrets, self.bk_history]
        card.row("Inclure les accès (Discord, Steam, Home Assistant)", self.bk_secrets)
        card.row("Inclure les historiques (jeux, débits, 24 h)", self.bk_history)
        card.row("Fichier .zip", hbox(self.button("Exporter…", self._export_backup, True),
                                      self.button("Importer…", self._import_backup)),
                 "À garder avant une réinstallation. À l'import, l'état actuel est d'abord "
                 "sauvegardé, puis l'appli redémarre.")

        card = self._card(lay, "Mises à jour")
        self.toggle("auto_update", card, "Se mettre à jour depuis GitHub",
                    "Toutes les 15 min. S'il y a des modifications locales, rien n'est écrasé.")
        card.row("Vérification", self.button("Vérifier maintenant", self._check_update))

    # --- actions ---

    def _check_update(self):
        if not instance.is_running():
            return self._flash("L'appli doit tourner pour vérifier les mises à jour.")
        config.save("flash_test.json", {"kind": "update", "at": time.time()})
        self._flash("Vérification demandée : le résultat s'affiche sur le G19.")

    def _control(self, action):
        def run():
            if action == "stop":
                instance.stop()
            else:
                if action == "restart":
                    instance.stop()
                if not instance.is_running():
                    instance.spawn()
        threading.Thread(target=run, daemon=True).start()
        self._flash({"start": "Démarrage…", "restart": "Redémarrage…", "stop": "Arrêt…"}[action])

    def _apply_flag(self, module, toggle, on):
        try:
            module.set_installed(on)
        except OSError as e:
            toggle.blockSignals(True)
            toggle.setChecked(not on)
            toggle.blockSignals(False)
            self._flash(f"Impossible : {e}")

    @staticmethod
    def _open(path):
        if Path(path).exists():
            os.startfile(path)

    def _export_backup(self):
        path, _ = QFileDialog.getSaveFileName(
            self, "Exporter les réglages", time.strftime("g19_reglages_%Y-%m-%d.zip"),
            "Sauvegarde G19 Monitor (*.zip)")
        if not path:
            return
        self.save(quiet=True)         # la sauvegarde contient aussi ce qui est affiché ici
        try:
            names = backup.export(path, self.bk_secrets.isChecked(), self.bk_history.isChecked())
        except OSError as e:
            return QMessageBox.critical(self, "G19 Monitor", f"Export impossible : {e}")
        self._flash(f"Exporté ({backup.describe(names)}) : {Path(path).name}")

    def _import_backup(self):
        path, _ = QFileDialog.getOpenFileName(self, "Importer des réglages", "",
                                              "Sauvegarde G19 Monitor (*.zip)")
        if not path:
            return
        try:
            names = backup.inspect(path)
        except (OSError, ValueError, KeyError) as e:
            return QMessageBox.critical(self, "G19 Monitor", f"Sauvegarde illisible : {e}")
        if QMessageBox.question(self, "G19 Monitor",
                                f"Remplacer par cette sauvegarde : {backup.describe(names)} ?\n\n"
                                "L'état actuel est d'abord sauvegardé dans le dossier des "
                                "données.") != QMessageBox.Yes:
            return
        try:
            _names, safety = backup.restore(path)
        except (OSError, ValueError) as e:
            return QMessageBox.critical(self, "G19 Monitor", f"Import impossible : {e}")
        if instance.is_running():
            self._control("restart")
        subprocess.Popen([sys.executable, str(Path(__file__).resolve())])
        QMessageBox.information(self, "G19 Monitor",
                                f"Importé. Copie de l'état précédent :\n{safety.name}")
        self._base = self.collect()   # pas de question « enregistrer ? » à la fermeture
        self.close()

    # --- réglages : lecture, enregistrement, synchronisation ---

    def collect(self):
        return {k: f.get() for k, f in self.fields.items()}

    def _dirty(self):
        return any(v != self._base.get(k) for k, v in self.collect().items())

    def save(self, quiet=False):
        """Enregistre ce qui a changé ici (appelé tout seul, peu après chaque changement)."""
        cur = self.collect()
        changes = {k: v for k, v in cur.items() if v != self._base.get(k)}
        if not changes:
            return
        settings.save_changes(changes)
        self._watch.poll()
        self._base = cur
        if not quiet:
            self._flash("✔ Enregistré — l'écran du G19 est à jour.")

    def closeEvent(self, e):
        self.save(quiet=True)       # dernier changement pas encore parti
        e.accept()

    def _sync_from_file(self):
        """Reprend les réglages changés ailleurs (menu du G19…), sauf ceux modifiés ici et pas
        encore enregistrés. Listes (pages, raccourcis, profils) : gardées telles quelles."""
        if not self._watch.poll():
            return
        s, cur = self._watch.settings, self.collect()
        dirty = {k for k, v in cur.items() if v != self._base.get(k)}
        changed = []
        for key, field in self.fields.items():
            if key in ("pages", "shortcuts", "audio_profiles") or key in dirty:
                continue
            value = theme_of(s) if key == "theme" else s.get(key)
            if value is not None and value != cur.get(key):
                field.set(value)
                changed.append(key)
        self.s = s
        if changed:
            now = self.collect()
            for key in changed:
                self._base[key] = now[key]
            self._flash("Réglages mis à jour depuis le G19.")

    def _flash(self, text):
        self.status.setText(text)
        QTimer.singleShot(5000, lambda: self.status.text() == text and self.status.setText(""))

    # --- thème ---

    def apply_theme(self, name):
        name = name or "dark"
        self.theme_name = name
        QApplication.instance().setStyleSheet(stylesheet(name))
        colors = palette(name)
        for t in self.toggles:
            t.colors = colors
            t.update()
        for i in range(self.nav.count()):
            it = self.nav.item(i)
            if it.data(Qt.UserRole):
                it.setIcon(glyph_icon(it.data(Qt.UserRole), colors["MUTED"], colors["ACCENT"]))
        title_bar(self, name)

    # --- aperçu et états ---

    def _load_ctx(self):
        from g19.media import MediaMonitor
        from g19_monitor import make_ctx

        self.ctx = make_ctx()
        self.media = MediaMonitor()

    def _press(self, button):
        if not instance.is_running():
            return self._flash("L'appli n'est pas lancée : les touches ne vont nulle part.")
        remote.send_key(button)
        if self.preview_page.currentData() != LIVE:
            self.preview_page.setCurrentIndex(0)     # on montre l'effet de la touche

    def _show(self, img):
        img = img.resize((int(320 * PREVIEW_SCALE), int(240 * PREVIEW_SCALE)), Image.LANCZOS)
        self.preview.setPixmap(pil_to_pixmap(img))

    def _update_preview(self, now, running):
        live = self.preview_page.currentData() == LIVE
        if live and running:
            if now - self._last_mirror_req >= 1:
                self._last_mirror_req = now
                remote.request_mirror()
            img = remote.read_mirror()
            if img is not None:
                return self._show(img)
        c = self.ctx
        if not c:
            return
        if now - self._last_sample >= 1:
            self._last_sample = now
            # chaque source à part : une qui échoue n'empêche pas l'aperçu
            for step in (c.stats.sample, lambda: c.gpu.sample(c.stats),
                         lambda: c.games.update(c.gpu.game, c.gpu.s, now),
                         lambda: setattr(c, "sessions", read_sessions(now)),
                         self._update_sources):
                try:
                    step()
                except Exception:
                    pass
        try:
            c.gpu.sample_fps()
        except Exception:
            pass
        c.media = self.media.state
        cfg = self.collect()
        page = self.preview_page.currentData()
        if page in (None, LIVE):
            page = cfg["pages"][0]
        if page not in cfg["pages"]:
            cfg["pages"] = cfg["pages"] + [page]
        c.settings = {**settings.DEFAULTS, **cfg}
        self._show(screen.adjust(render(page, c, now), c.settings))

    def changed(self, *_args):
        """Un contrôle a bougé : enregistrement un instant plus tard (un curseur qu'on fait
        glisser n'écrit qu'une fois)."""
        self.save_timer.start(600)

    def _wire(self, widget):
        """Branche l'enregistrement automatique sur tous les contrôles de la fenêtre."""
        from PySide6.QtWidgets import QAbstractButton, QComboBox, QLineEdit, QSlider, QSpinBox
        for w in widget.findChildren(QAbstractButton):
            if w.isCheckable():
                w.toggled.connect(self.changed)
        for w in widget.findChildren(QComboBox):
            w.currentIndexChanged.connect(self.changed)
        for w in widget.findChildren(QSpinBox):
            w.valueChanged.connect(self.changed)
        for w in widget.findChildren(QSlider):
            w.valueChanged.connect(self.changed)
        for w in widget.findChildren(QLineEdit):
            if w.parent() and isinstance(w.parent(), QSpinBox):
                continue
            w.editingFinished.connect(self.changed)     # texte : une fois la saisie finie
        self.pages.model().rowsMoved.connect(self.changed)
        self.pages.itemChanged.connect(self.changed)

    def _tick(self):
        now = time.time()
        running = instance.is_running()
        try:
            if now - self._update_at >= 1:
                self._update_at = now
                st = (settings.load_state().get("update_status") or {}).get("text", "")
                self.update_label.setText(f"Mises à jour : {st}" if st else "")
                self.state_pill.setText("● en marche" if running else "○ arrêtée")
                self.state_pill.setObjectName("pillOn" if running else "pillOff")
                self.state_pill.style().polish(self.state_pill)
                for b in self._pad_buttons:
                    b.setEnabled(running)
                self.pad_hint.setText("clic sur l'aperçu puis flèches · Entrée = OK · Échap = "
                                      "Annuler · M = Menu" if running else
                                      "lance l'appli pour piloter le G19")
                self._sync_from_file()
            live = self.preview_page.currentData() == LIVE
            if live or now - getattr(self, "_frame_at", 0) >= 0.25:
                self._frame_at = now
                self._update_preview(now, running)
        except Exception as e:          # une erreur d'aperçu ne doit pas fermer la fenêtre
            self.status.setText(f"aperçu : {e.__class__.__name__}: {e}")

    def _update_sources(self):
        c = self.ctx

        def ok(b):
            return "✔" if b else "✘"

        steam = c.games.steam
        self.sources.setText("\n".join([
            f"{ok(afterburner.read_sensors() is not None)} MSI Afterburner",
            f"{ok(rtss.read_apps() is not None)} RivaTuner (FPS)",
            f"{ok(bool(c.gpu.lhm.sensors))} LibreHardwareMonitor",
            f"{ok(steam and steam.apps)} Steam" + (f" ({len(steam.apps)} jeux)" if steam else ""),
            f"{ok(c.discord.status == 'connecté')} Discord : {c.discord.status}",
            f"{ok(c.notifs.status == 'ok')} Notifications Windows : {c.notifs.status}",
            f"{ok(c.volume.level is not None)} Audio : {c.volume.device or '—'}",
            f"{ok(c.vpn.ts and c.vpn.ts['running'])} Tailscale : "
            + ((c.vpn.ts or {}).get("state") or ("non installé" if not c.vpn.installed else "—")),
            f"{ok(c.fuel and not c.fuel.status)} Home Assistant : {c.fuel.status or 'connecté'}"
            if c.fuel else "",
        ]).strip())


def main():
    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)
    app = QApplication(sys.argv)
    app.setApplicationName("G19 Monitor")
    win = ConfigApp()
    win.show()
    title_bar(win, win.theme_name)    # la fenêtre doit exister pour teinter sa barre de titre
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
