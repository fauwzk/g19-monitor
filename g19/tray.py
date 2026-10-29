"""Icône dans la zone de notification Windows : voyant Claude, menu des pages, configuration."""
import os
import queue
import subprocess
import sys

import pystray
from PIL import Image, ImageDraw

from . import instance
from .render import ACCENT, BG, CLAUDE, DISCORD, GPU_C, OK, PANEL, RAM_C, STATE_COLOR, TRACK
from .settings import PAGE_TITLES

SIZE = 64


def make_icon(state=None, unread=False):
    """Mini écran G19 (trois barres), avec la pastille d'état Claude en bas à droite."""
    s = SIZE * 4  # dessiné en grand puis réduit pour l'anticrénelage
    img = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle((8, 24, s - 8, s - 24), 36, fill=PANEL, outline=TRACK, width=8)
    d.rounded_rectangle((28, 44, s - 28, s - 44), 16, fill=BG)
    for i, (color, frac) in enumerate(((ACCENT, 0.75), (GPU_C, 0.5), (RAM_C, 0.9))):
        y = 70 + i * 40
        d.rounded_rectangle((48, y, s - 48, y + 20), 10, fill=TRACK)
        d.rounded_rectangle((48, y, 48 + (s - 96) * frac, y + 20), 10, fill=color)
    if unread:
        d.ellipse((4, s - 92, 88, s - 8), fill=DISCORD, outline=BG, width=10)
    if state:
        d.ellipse((s - 104, s - 104, s - 4, s - 4), fill=STATE_COLOR.get(state, CLAUDE),
                  outline=BG, width=12)
    return img.resize((SIZE, SIZE), Image.LANCZOS)


def open_config():
    exe = sys.executable.replace("python.exe", "pythonw.exe")
    subprocess.Popen([exe, str(instance.APP_DIR / "config_g19.pyw")], cwd=instance.APP_DIR,
                     creationflags=subprocess.DETACHED_PROCESS)


class Tray:
    """Les clics du menu arrivent dans `commands` : ("page", id), ("restart",), ("quit",)."""

    def __init__(self):
        self.commands = queue.Queue()
        self.pages = list(PAGE_TITLES)
        self.page = None
        self._key = None
        self.icon = pystray.Icon("G19Monitor", make_icon(), "G19 Monitor", self._menu())
        self.icon.run_detached()

    def _menu(self):
        def page_item(pid):
            return pystray.MenuItem(PAGE_TITLES[pid], lambda: self.commands.put(("page", pid)),
                                    checked=lambda _: self.page == pid, radio=True)

        return pystray.Menu(
            pystray.MenuItem("Configuration…", lambda: open_config(), default=True),
            pystray.MenuItem("Afficher sur le G19",
                             pystray.Menu(lambda: (page_item(p) for p in self.pages))),
            pystray.MenuItem("Lancer un test de débit", lambda: self.commands.put(("speedtest",))),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Journal", lambda: _open(instance.APP_DIR / "g19.log")),
            pystray.MenuItem("Redémarrer", lambda: self.commands.put(("restart",))),
            pystray.MenuItem("Quitter", lambda: self.commands.put(("quit",))),
        )

    def update(self, page, pages, sessions, tooltip, unread=False):
        self.page = page
        if pages != self.pages:
            self.pages = list(pages)
            self.icon.update_menu()
        state = sessions[0].state if sessions else None
        key = (state, bool(unread))
        if key != self._key:
            self._key = key
            self.icon.icon = make_icon(state, unread)
        tooltip = tooltip[:127]
        if self.icon.title != tooltip:
            self.icon.title = tooltip

    def stop(self):
        try:
            self.icon.stop()
        except Exception:
            pass


def _open(path):
    if path.exists():
        os.startfile(path)
