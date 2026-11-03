"""Où part le temps de rendu (cProfile), avec les réglages de l'appli : python3 tools/linux_profile.py"""
import cProfile
import os
import pstats
import statistics
import sys
import time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from g19.linux import compat  # noqa: E402
compat.install()
import g19_monitor as m  # noqa: E402
from g19 import render, settings  # noqa: E402

c = m.make_ctx()
cfg = settings.load()
c.settings, c.pages = cfg, cfg["pages"]
c.stats.sample()
c.gpu.sample(c.stats)
t = time.time()
per = {}
for p in c.pages:
    render.render(p, c, t)
    v = []
    for k in range(5):
        a = time.perf_counter()
        render.render(p, c, t + k / 30)
        v.append((time.perf_counter() - a) * 1000)
    per[p] = statistics.median(v)
print("par page (ms) :", "  ".join(f"{p} {v:.1f}" for p, v in sorted(per.items(), key=lambda kv: -kv[1])))
for variant, extra in (("sans fond d'écran", {"wallpaper_bg": False}),
                       ("sans formes lissées", {"smooth_shapes": False}),
                       ("thème sombre", {"theme": "dark"})):
    c.settings = {**cfg, **extra}
    render.render("system", c, t)
    a = time.perf_counter()
    for k in range(10):
        render.render("system", c, t + k / 30)
    print(f"Système, {variant} : {(time.perf_counter() - a) * 100:.1f} ms")
c.settings = cfg
pr = cProfile.Profile()
pr.enable()
for k in range(20):
    render.render("system", c, t + k / 30)
pr.disable()
pstats.Stats(pr).sort_stats("tottime").print_stats(14)
os._exit(0)
