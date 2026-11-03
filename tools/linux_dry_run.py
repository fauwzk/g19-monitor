"""Boucle principale de l'appli pendant N s, avec un faux écran (rien n'est envoyé au G19) :
attrape les erreurs avant un vrai lancement. python3 tools/linux_dry_run.py [secondes]"""
import os
import sys
import threading
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.chdir(ROOT)
os.environ.setdefault("G19_NO_GUARD", "1")
SECONDS = float(sys.argv[1]) if len(sys.argv) > 1 else 15
sys.argv = [sys.argv[0]]

import g19_monitor as m  # noqa: E402


class FakeScreen:
    sent = 0

    def show(self, img):
        assert img.size == (320, 240), img.size
        self.sent += 1

    def update(self):
        pass

    def pressed(self):
        return set()

    def close(self):
        pass


screen = FakeScreen()
m.connect_lcd = lambda inst, tray: screen
m.setup_logging()


def stop_later():
    time.sleep(SECONDS)
    m.instance._lx.stop(5, m.instance.MUTEX, m.instance.QUIT_EVENT) if os.name != "nt" \
        else m.instance.stop()


threading.Thread(target=stop_later, daemon=True).start()
start = time.time()
code = m.run()
print(f"fin : code {code}, {screen.sent} images en {time.time() - start:.1f} s")
os._exit(0)
