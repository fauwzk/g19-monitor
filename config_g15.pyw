"""Utilitaire de réglages de G15 Monitor (écran monochrome des G15 / G510 / G13), à part de
celui du G19 : lancer / arrêter l'appli, démarrage avec Windows, pages et leur ordre,
affichage ; aperçu en direct de l'écran 160×43. Enregistrement automatique dans
g15_settings.json (l'appli le relit toute seule)."""
import sys
import threading
import time
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(APP_DIR))

from PySide6.QtCore import QObject, QSize, Qt, QTimer, Signal  # noqa: E402
from PySide6.QtGui import QIcon  # noqa: E402
from PySide6.QtWidgets import (QAbstractItemView, QApplication, QHBoxLayout, QLabel,  # noqa: E402
                               QListWidget, QListWidgetItem, QMainWindow, QPushButton,
                               QScrollArea, QVBoxLayout, QWidget)

from g19 import config, instance, mono  # noqa: E402
from g19.qtkit import (Card, Toggle, bind_spin, bind_toggle, hbox, label,  # noqa: E402
                       pil_to_pixmap, spin, stylesheet, title_bar)

THEME = "g15"                 # palette « Rétro G15 » de l'utilitaire
SETTINGS_FILE = "g15_settings.json"
DEFAULTS = {"pages": list(mono.DEFAULT_PAGES), "fps": 8, "banners": True,
            "volume_popup": True, "banner_seconds": 4, "auto_launch": True}
SCALE = 3                     # aperçu : 480×129
PREVIEW_FPS = 30


def load_settings():
    data = config.load(SETTINGS_FILE, None) or {}
    cfg = {**DEFAULTS, **data}
    cfg["pages"] = [p for p in cfg["pages"] if p in mono.PAGES] or list(DEFAULTS["pages"])
    return cfg


def preview_icon():
    from PIL import Image, ImageDraw
    img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle((4, 18, 60, 46), 6, fill=(30, 34, 28), outline=(90, 96, 88), width=2)
    d.rectangle((10, 24, 54, 40), fill=(158, 190, 90))
    for k, w in enumerate((30, 20)):
        d.rectangle((13, 27 + k * 6, 13 + w, 30 + k * 6), fill=(30, 34, 28))
    return img


class Bridge(QObject):
    call = Signal(object)


class ConfigG15(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("G15 Monitor — réglages")
        self.setWindowIcon(QIcon(pil_to_pixmap(preview_icon())))
        self.s = load_settings()
        self.fields = {}
        self.ctx = None
        self._last_sample = 0.0
        self.bridge = Bridge()
        self.bridge.call.connect(lambda fn: fn())
        QApplication.instance().setStyleSheet(stylesheet(THEME))

        root = QWidget()
        self.setCentralWidget(root)
        lay = QHBoxLayout(root)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        # colonne de gauche : réglages
        left = QWidget()
        ll = QVBoxLayout(left)
        ll.setContentsMargins(24, 20, 16, 20)
        ll.setSpacing(14)
        ll.addWidget(label("G15 Monitor", "pageTitle"))
        ll.addWidget(label("Écran monochrome des G15, G510 et G13. Tourne à côté de G19 Monitor ; "
                           "les réglages sont enregistrés tout de suite.", "pageHint", wrap=True))
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        inner = QWidget()
        il = QVBoxLayout(inner)
        il.setContentsMargins(0, 0, 8, 0)
        il.setSpacing(14)
        il.addWidget(self._state_card())
        il.addWidget(self._pages_card())
        il.addWidget(self._display_card())
        il.addStretch(1)
        scroll.setWidget(inner)
        ll.addWidget(scroll, 1)
        lay.addWidget(left, 1)

        # colonne de droite : aperçu
        lay.addWidget(self._preview_panel())

        self.save_timer = QTimer(self)
        self.save_timer.setSingleShot(True)
        self.save_timer.timeout.connect(self.save)
        threading.Thread(target=self._load_ctx, daemon=True).start()
        self.resize(1080, 640)
        self.timer = QTimer(self)
        self.timer.setTimerType(Qt.PreciseTimer)
        self.timer.timeout.connect(self._tick)
        self.timer.start(1000 // PREVIEW_FPS)

    # --- cartes ---

    def _state_card(self):
        card = Card("État")
        self.state_pill = label("", "pillOff")
        self.start_btn = QPushButton("Lancer")
        self.start_btn.setObjectName("accent")
        self.start_btn.clicked.connect(self._start_stop)
        card.row("G15 Monitor", hbox(self.state_pill, self.start_btn),
                 "L'applet « PC Monitor (G15) » dans Logitech Gaming Software.")
        guard = QPushButton("Panneau du gardien")
        guard.clicked.connect(self._open_guard)
        card.row("Gardien", guard,
                 "Démarrage avec Windows, lancement au branchement du clavier, état des deux "
                 "applis.")
        self.g19_note = card.note("")
        return card

    def _pages_card(self):
        card = Card("Pages")
        self.pages = QListWidget()
        self.pages.setDragDropMode(QAbstractItemView.InternalMove)
        self.pages.setUniformItemSizes(True)
        self.pages.setMinimumHeight(8 * 30 + 6)
        enabled = self.s["pages"]
        for pid in enabled + [p for p in mono.PAGES if p not in enabled]:
            it = QListWidgetItem(mono.PAGES[pid])
            it.setData(Qt.UserRole, pid)
            it.setFlags(it.flags() | Qt.ItemIsUserCheckable | Qt.ItemIsDragEnabled)
            it.setCheckState(Qt.Checked if pid in enabled else Qt.Unchecked)
            it.setSizeHint(QSize(0, 30))
            self.pages.addItem(it)
        self.pages.model().rowsMoved.connect(self.changed)
        self.pages.itemChanged.connect(self.changed)
        self.pages.currentItemChanged.connect(
            lambda it, _old: it and self._show_page(it.data(Qt.UserRole)))
        card.widget(self.pages)
        card.note("Coche les pages à afficher, glisse-les pour l'ordre (touches 1 et 2 sous "
                  "l'écran). Cliquer une page la montre dans l'aperçu.")
        return card

    def _display_card(self):
        card = Card("Affichage")
        self._toggle(card, "banners", "Bandeaux",
                     "Notifications Windows, changement de morceau, lecture / pause, micro.")
        self._spin(card, "banner_seconds", "Durée des bandeaux", 2, 15, "s")
        self._toggle(card, "volume_popup", "Fenêtre de volume",
                     "Quand le son change, son niveau en encadré par-dessus la page.")
        self._spin(card, "fps", "Images par seconde", 2, 30, "",
                   "8 suffit : l'écran monochrome est lent à se rafraîchir.")
        return card

    def _toggle(self, card, key, text, hint=None):
        w = Toggle(bool(self.s.get(key)))
        w.toggled.connect(self.changed)
        card.row(text, w, hint)
        self.fields[key] = bind_toggle(w)

    def _spin(self, card, key, text, lo, hi, suffix="", hint=None):
        w = spin(lo, hi, 1, suffix)
        w.setValue(int(self.s.get(key) or lo))
        w.valueChanged.connect(self.changed)
        card.row(text, w, hint)
        self.fields[key] = bind_spin(w)

    def _preview_panel(self):
        box = QWidget()
        box.setObjectName("previewBox")
        lay = QVBoxLayout(box)
        lay.setContentsMargins(16, 20, 24, 20)
        lay.setSpacing(10)
        lay.addWidget(label("APERÇU", "section"))
        self.preview = QLabel("chargement…")
        self.preview.setFixedSize(mono.W * SCALE, mono.H * SCALE)
        self.preview.setAlignment(Qt.AlignCenter)
        lay.addWidget(self.preview)
        # les 4 touches sous l'écran : ici elles changent la page de l'aperçu
        keys = QHBoxLayout()
        keys.setSpacing(6)
        for text, step in (("◄", -1), ("►", 1)):
            b = QPushButton(text)
            b.setFixedWidth(mono.W * SCALE // 4 - 6)
            b.clicked.connect(lambda _=False, s=step: self._step_page(s))
            keys.addWidget(b)
        self.action_keys = []
        for _ in range(2):
            b = QPushButton("")
            b.setEnabled(False)
            b.setFixedWidth(mono.W * SCALE // 4 - 6)
            keys.addWidget(b)
            self.action_keys.append(b)
        lay.addLayout(keys)
        self.page_label = label("", "hint")
        lay.addWidget(self.page_label)
        lay.addWidget(label("L'aperçu est calculé ici avec les mêmes capteurs que l'appli. "
                            "◄ ► changent sa page ; les deux autres touches montrent leur rôle "
                            "sur le clavier pour cette page.", "hint", wrap=True))
        lay.addStretch(1)
        self.preview_page = self.s["pages"][0]
        self._update_keys()
        return box

    # --- pages de l'aperçu ---

    def _show_page(self, pid):
        self.preview_page = pid
        self._update_keys()

    def _step_page(self, step):
        pages = self.collect()["pages"]
        i = pages.index(self.preview_page) if self.preview_page in pages else 0
        self.preview_page = pages[(i + step) % len(pages)]
        self._update_keys()

    def _update_keys(self):
        acts = mono.ACTIONS.get(self.preview_page, ("", ""))
        names = {"playpause": "lecture", "next": "suivant"}
        for b, a in zip(self.action_keys, acts):
            b.setText(names.get(a, a))
        self.page_label.setText(f"Page : {mono.PAGES.get(self.preview_page, '')}")

    # --- réglages ---

    def collect(self):
        pages = []
        for i in range(self.pages.count()):
            it = self.pages.item(i)
            if it.checkState() == Qt.Checked:
                pages.append(it.data(Qt.UserRole))
        out = {k: f.get() for k, f in self.fields.items()}
        out["pages"] = pages or [mono.DEFAULT_PAGES[0]]
        return out

    def changed(self, *_args):
        self.save_timer.start(600)

    def save(self):
        data = {**load_settings(), **self.collect()}
        try:
            config.save(SETTINGS_FILE, data)
        except OSError as e:
            self.page_label.setText(f"enregistrement impossible : {e}")

    # --- appli : lancer / arrêter ---

    def _open_guard(self):
        instance._popen([str(APP_DIR / "config_guard.pyw")])

    def _start_stop(self):
        if instance.is_running(instance.MONO_MUTEX):
            threading.Thread(target=lambda: instance.stop(
                mutex=instance.MONO_MUTEX, quit_event=instance.MONO_QUIT_EVENT),
                daemon=True).start()
        else:
            instance._popen([str(instance.MONO_MAIN)])

    # --- aperçu ---

    def _load_ctx(self):
        from g15_monitor import Ctx
        ctx = Ctx()
        self.bridge.call.emit(lambda: setattr(self, "ctx", ctx))

    def _tick(self):
        now = time.time()
        running = instance.is_running(instance.MONO_MUTEX)
        self.state_pill.setText("● en marche" if running else "○ arrêtée")
        self.state_pill.setObjectName("pillOn" if running else "pillOff")
        self.state_pill.style().polish(self.state_pill)
        self.start_btn.setText("Arrêter" if running else "Lancer")
        self.g19_note.setText("G19 Monitor tourne aussi sur ce PC : chaque clavier garde son "
                              "écran." if instance.is_running() else "")
        c = self.ctx
        if not c:
            return
        if now - self._last_sample >= 1:
            self._last_sample = now
            for step in (c.stats.sample, lambda: c.gpu.sample(c.stats), c.gpu.sample_fps):
                try:
                    step()
                except Exception:
                    pass
            try:
                from g19.claude_status import read_sessions
                c.sessions = read_sessions(now)
            except Exception:
                pass
        c.media = c.media_monitor.state
        try:
            img = mono.render(self.preview_page, c, now)
        except Exception as e:
            self.page_label.setText(f"aperçu : {e.__class__.__name__}: {e}")
            return
        self.preview.setPixmap(pil_to_pixmap(mono.lcd_style(img, SCALE)))


def main():
    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)
    app = QApplication(sys.argv)
    app.setApplicationName("G15 Monitor")
    win = ConfigG15()
    win.show()
    title_bar(win, THEME)
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
