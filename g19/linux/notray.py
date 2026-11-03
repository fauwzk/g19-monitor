"""Pas d'icône dans la barre des tâches (pystray absent) : même interface que g19.tray, sans
rien afficher. Les commandes viennent alors des touches du G19 et de l'utilitaire."""
import queue
import subprocess
import sys
from types import SimpleNamespace

from .. import instance


def open_config():
    subprocess.Popen([sys.executable, str(instance.APP_DIR / "config_g19.pyw")],
                     cwd=instance.APP_DIR, start_new_session=True)


class Tray:
    def __init__(self, *args, **kw):
        self.commands = queue.Queue()
        self.icon = SimpleNamespace(title="G19 Monitor")

    def update(self, *args, **kw):
        pass

    def stop(self):
        pass
