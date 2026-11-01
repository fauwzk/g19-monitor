"""Panneau du gardien : état du gardien et démarrage avec Windows, claviers branchés, état de
chaque appli (G19 Monitor, G15 Monitor) avec Lancer / Arrêter / Réglages, et son journal.

Le gardien publie son état dans guard_state.json à chaque passage (toutes les 5 s) ; les
claviers sont aussi relus ici, pour réagir tout de suite à un branchement."""
import subprocess
import sys
import threading
import time
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(APP_DIR))

from PySide6.QtCore import Qt, QTimer  # noqa: E402
from PySide6.QtGui import QIcon  # noqa: E402
from PySide6.QtWidgets import (QApplication, QMainWindow, QPlainTextEdit, QPushButton,  # noqa: E402
                               QScrollArea, QVBoxLayout, QWidget)

import install_startup  # noqa: E402
from g19 import config, instance, keyboards, settings  # noqa: E402
from g19.qtkit import (Card, Toggle, hbox, hexa, label, mix, palette, pil_to_pixmap,  # noqa: E402
                       stylesheet, title_bar)

STATE_MAX_AGE = 15        # s : au-delà, l'état publié est périmé (gardien arrêté)
LOG_LINES = 14


def icon_image():
    from PIL import Image, ImageDraw
    img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.polygon([(32, 4), (56, 14), (52, 42), (32, 60), (12, 42), (8, 14)], fill=(60, 130, 220),
              outline=(20, 40, 80))
    d.line((20, 32, 29, 42, 45, 22), fill=(255, 255, 255), width=6)
    return img


def open_utility(script):
    exe = Path(sys.executable)
    pyw = exe.with_name("pythonw.exe")
    subprocess.Popen([str(pyw if pyw.exists() else exe), str(APP_DIR / script)], cwd=APP_DIR,
                     creationflags=subprocess.DETACHED_PROCESS)


def guard_log(n=LOG_LINES):
    """Dernières lignes du gardien dans g19.log."""
    path = APP_DIR / "g19.log"
    try:
        with open(path, "rb") as f:
            f.seek(0, 2)
            f.seek(max(0, f.tell() - 200_000))
            lines = f.read().decode("utf-8", errors="replace").splitlines()
    except OSError:
        return []
    return [l.replace(" INFO gardien : ", "  ") for l in lines if " gardien : " in l][-n:]


APPS = (
    {"key": "g19", "name": "G19 Monitor", "kb": "color", "keyboard": "G19",
     "mutex": instance.MUTEX, "config": "config_g19.pyw"},
    {"key": "g15", "name": "G15 Monitor", "kb": "mono", "keyboard": "G15 / G510 / G13",
     "mutex": instance.MONO_MUTEX, "config": "config_g15.pyw"},
)


class GuardPanel(QMainWindow):
    def __init__(self, theme):
        super().__init__()
        self.theme = theme
        self.setWindowTitle("G19 Monitor — gardien")
        self.setWindowIcon(QIcon(pil_to_pixmap(icon_image())))
        QApplication.instance().setStyleSheet(stylesheet(theme))
        self.kb = None
        self._kb_at = 0.0

        root = QWidget()
        self.setCentralWidget(root)
        outer = QVBoxLayout(root)
        outer.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        outer.addWidget(scroll)
        inner = QWidget()
        lay = QVBoxLayout(inner)
        lay.setContentsMargins(24, 20, 24, 20)
        lay.setSpacing(14)
        scroll.setWidget(inner)
        lay.addWidget(label("Gardien", "pageTitle"))
        lay.addWidget(label("Il démarre avec Windows, lance l'appli de chaque clavier branché et "
                            "relance celle qui plante.", "pageHint", wrap=True))

        # gardien
        card = Card("Gardien")
        self.guard_pill = label("", "pillOff")
        self.guard_btn = QPushButton("Démarrer")
        self.guard_btn.setObjectName("accent")
        self.guard_btn.clicked.connect(self._guard_toggle)
        card.row("Gardien", hbox(self.guard_pill, self.guard_btn), None)
        self.guard_info = label("", "hint", wrap=True)
        card.widget(self.guard_info)
        auto = Toggle(install_startup.is_installed())
        auto.toggled.connect(self._startup)
        self.startup_toggle = auto
        card.row("Lancer avec Windows", auto,
                 "Une seule entrée de démarrage : le gardien, qui lance ensuite les applis.")
        lay.addWidget(card)

        # claviers
        card = Card("Claviers branchés")
        self.kb_labels = {}
        for a in APPS:
            w = label("", "pillOff")
            self.kb_labels[a["kb"]] = w
            card.row(a["keyboard"], w, None)
        self.kb_note = card.note("")
        lay.addWidget(card)

        # applis
        card = Card("Applis")
        self.rows = {}
        for a in APPS:
            pill = label("", "pillOff")
            start = QPushButton("Lancer")
            start.clicked.connect(lambda _=False, a=a: self._app_toggle(a))
            cfg = QPushButton("Réglages")
            cfg.clicked.connect(lambda _=False, a=a: open_utility(a["config"]))
            hint = label("", "hint", wrap=True)
            box = QWidget()
            bl = QVBoxLayout(box)
            bl.setContentsMargins(0, 0, 0, 0)
            bl.setSpacing(2)
            bl.addWidget(hbox(pill, start, cfg))
            card.row(a["name"], box, None)
            card.widget(hint)
            self.rows[a["key"]] = (pill, start, hint)
        auto15 = Toggle(bool(self._g15_settings().get("auto_launch", True)))
        auto15.toggled.connect(self._g15_auto)
        card.row("Le gardien s'occupe de G15 Monitor", auto15,
                 "Lancement au branchement d'un G15 / G510 / G13 et relance s'il plante.")
        lay.addWidget(card)

        # journal
        card = Card("Journal du gardien")
        self.log_view = QPlainTextEdit()
        self.log_view.setReadOnly(True)
        p = palette(theme)
        self.log_view.setStyleSheet(
            f"QPlainTextEdit {{ background: {hexa(mix(p['BG'], p['PANEL'], 0.5))}; "
            f"color: {hexa(p['MUTED'])}; border: 1px solid {hexa(p['LINE'])}; "
            "border-radius: 6px; padding: 6px; font-family: Consolas; font-size: 9pt; }")
        self.log_view.setMinimumHeight(LOG_LINES * 18)
        card.widget(self.log_view)
        lay.addWidget(card)
        lay.addStretch(1)

        self.resize(640, 820)
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._tick)
        self.timer.start(1000)
        self._tick()

    # --- actions ---

    def _startup(self, on):
        try:
            install_startup.set_installed(on)
        except OSError as e:
            self.startup_toggle.blockSignals(True)
            self.startup_toggle.setChecked(not on)
            self.startup_toggle.blockSignals(False)
            self.guard_info.setText(f"démarrage avec Windows : {e}")

    def _guard_toggle(self):
        if instance.guard_running():
            instance.stop_guard()
        else:
            instance.start_guard()

    def _app_toggle(self, a):
        if instance.is_running(a["mutex"]):
            def stop():
                if a["key"] == "g19":
                    instance.stop()
                else:
                    instance.stop(mutex=instance.MONO_MUTEX,
                                  quit_event=instance.MONO_QUIT_EVENT)
            threading.Thread(target=stop, daemon=True).start()
        elif a["key"] == "g19":
            instance.spawn()
        else:
            instance._popen([str(instance.MONO_MAIN)])

    @staticmethod
    def _g15_settings():
        data = config.load("g15_settings.json", None)
        return data if isinstance(data, dict) else {}

    def _g15_auto(self, on):
        data = self._g15_settings()
        data["auto_launch"] = bool(on)
        try:
            config.save("g15_settings.json", data)
        except OSError:
            pass

    # --- affichage ---

    @staticmethod
    def _pill(w, text, on):
        w.setText(text)
        w.setObjectName("pillOn" if on else "pillOff")
        w.style().polish(w)

    def _tick(self):
        now = time.time()
        running = instance.guard_running()
        state = config.load(instance.GUARD_STATE, None) or {}
        fresh = running and now - state.get("at", 0) < STATE_MAX_AGE
        self._pill(self.guard_pill, "● en marche" if running else "○ arrêté", running)
        self.guard_btn.setText("Arrêter" if running else "Démarrer")
        if fresh:
            since = time.strftime("%d/%m %H:%M", time.localtime(state.get("started", now)))
            how = "au démarrage de Windows" if state.get("boot") else "par une appli"
            self.guard_info.setText(f"Lancé {how}, le {since} (processus {state.get('pid')}). "
                                    "Arrêter le gardien laisse les applis tourner.")
        else:
            self.guard_info.setText("Sans gardien, rien ne relance une appli qui plante et un "
                                    "clavier branché ne lance pas son appli." if not running
                                    else "En attente de son premier passage…")
        if now - self._kb_at >= 2:
            self.kb, self._kb_at = keyboards.detect(), now
        kb = self.kb
        for a in APPS:
            w = self.kb_labels[a["kb"]]
            if kb is None:
                self._pill(w, "inconnu", False)
            else:
                self._pill(w, "● branché" if kb[a["kb"]] else "○ absent", kb[a["kb"]])
        self.kb_note.setText("Détection impossible (bibliothèque hidapi absente) : le gardien ne "
                             "gère que G19 Monitor." if kb is None else "")
        apps = state.get("apps", {}) if fresh else {}
        for a in APPS:
            pill, start, hint = self.rows[a["key"]]
            on = instance.is_running(a["mutex"])
            info = apps.get(a["key"], {})
            self._pill(pill, "● en marche" if on else "○ arrêtée", on)
            start.setText("Arrêter" if on else "Lancer")
            present = kb[a["kb"]] if kb else (a["key"] == "g19")
            if not running:
                text = "Gardien arrêté : pas de lancement ni de relance automatique."
            elif a["key"] == "g15" and not info.get("enabled", True):
                text = "Non géré par le gardien (jamais lancée, ou option coupée ci-dessous)."
            elif info.get("stopped"):
                text = "Quittée exprès : relancée au prochain branchement du clavier."
            elif not present:
                text = "Clavier absent : lancée dès qu'il sera branché."
            elif on:
                n = info.get("launches", 0)
                text = "Surveillée : relancée si elle plante." + (
                    f" {n} relance{'s' if n > 1 else ''} ces 10 dernières minutes." if n else "")
            else:
                text = "Clavier branché : le gardien va la lancer."
            hint.setText(text)
        lines = guard_log()
        text = "\n".join(lines)
        if self.log_view.toPlainText() != text:
            self.log_view.setPlainText(text)
            self.log_view.verticalScrollBar().setValue(
                self.log_view.verticalScrollBar().maximum())


def main():
    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)
    app = QApplication(sys.argv)
    app.setApplicationName("G19 Monitor — gardien")
    theme = settings.load().get("theme", "dark")
    win = GuardPanel(theme)
    win.show()
    title_bar(win, theme)
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
