"""Coût d'une image sur cette machine, avec les réglages de l'appli (lus, jamais écrits)."""
import os
import statistics
import sys
import time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from g19.linux import compat  # noqa: E402
compat.install()
import g19_monitor as m  # noqa: E402
from g19 import render, screen, settings, night  # noqa: E402
from g19.usb_lcd import frame_bytes  # noqa: E402

c = m.make_ctx()
cfg = settings.load()
c.settings = cfg
c.stats.sample()
c.gpu.sample(c.stats)
pages = cfg["pages"]
c.pages = pages
steps = {}


def timed(name, fn, *a):
    t0 = time.perf_counter()
    r = fn(*a)
    steps.setdefault(name, []).append((time.perf_counter() - t0) * 1000)
    return r


t = time.time()
for p in pages:
    render.render(p, c, t)
for k in range(6):
    for p in pages:
        img = timed("rendu", render.render, p, c, t + k / 30)
        img = timed("retouches", screen.adjust, img, cfg)
        img = timed("tramage", screen.dither, img, cfg)
        timed("conversion USB", frame_bytes, img)
tot = 0
print("thème", cfg.get("theme"), "· fond", cfg.get("wallpaper_bg"), "· réglage", cfg.get("fps"), "i/s")
for k, v in steps.items():
    med = statistics.median(v)
    tot += med
    print(f"  {k:15s} {med:6.1f} ms  (max {max(v):5.1f})")
print(f"  total ~{tot:.1f} ms → {1000 / tot:.0f} i/s au mieux ; budget à {cfg.get('fps')} i/s : "
      f"{1000 / cfg.get('fps', 15):.1f} ms")
worst = sorted(((statistics.median(v), p) for p in pages
                for v in [[0]]), reverse=True)
os._exit(0)
