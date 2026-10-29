"""Captures du README (docs/images) avec des données de démonstration : capteurs réels (rien
de personnel), mais média, Discord, Steam, sessions Claude, jeux, ville… inventés.
Ne jamais publier de captures faites avec les vraies données (comptes, amis, pochettes).

    python tools/readme_shots.py
"""
import io
import math
import sys
import time
from collections import deque
from pathlib import Path
from types import SimpleNamespace as NS

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.argv = [sys.argv[0]]

import g19_monitor as m  # noqa: E402
from g19 import render, settings  # noqa: E402
from g19.away import Away  # noqa: E402
from g19.claude_status import Session  # noqa: E402
from g19.coverflow import Coverflow  # noqa: E402
from g19.gpu import GpuMonitor  # noqa: E402
from g19.media import MediaState, _prepare_art  # noqa: E402
from g19.menu import SettingsMenu  # noqa: E402
from PIL import Image, ImageDraw, ImageFilter  # noqa: E402

from g19 import wallpaper  # noqa: E402

# pas le fond d'écran de ce PC sur des captures publiques (Aero prend alors son dégradé)
wallpaper.image = lambda *a, **k: None

OUT = ROOT / "docs" / "images"
OUT.mkdir(parents=True, exist_ok=True)
SCALE = 2


def cover_art():
    """Pochette inventée : coucher de soleil synthwave (dessinée ici, aucun droit tiers)."""
    s = 512
    img = Image.new("RGB", (s, s))
    d = ImageDraw.Draw(img)
    for y in range(s):
        f = y / s
        d.line((0, y, s, y), fill=(int(40 + 200 * f), int(20 + 40 * f), int(90 - 40 * f)))
    for k in range(12):                         # soleil à bandes
        y0 = 150 + k * 18
        d.chord((136, 120, 376, 360), 180, 360, fill=(255, 180 - k * 8, 60 + k * 6))
    for k in range(7):
        y = 250 + k * 16
        d.rectangle((120, y, 392, y + 3 + k), fill=(40 + 20 * k, 20, 90))
    for k in range(-8, 9):                      # grille au sol
        d.line((256 + k * 10, 330, 256 + k * 90, s), fill=(255, 80, 200), width=2)
    y, step = 336, 6
    while y < s:
        d.line((0, y, s, y), fill=(255, 80, 200), width=2)
        step *= 1.4
        y += int(step)
    d.rectangle((0, 300, s, 332), fill=(30, 10, 60))
    img = img.filter(ImageFilter.GaussianBlur(0.6))
    buf = io.BytesIO()
    img.save(buf, "PNG")
    return buf.getvalue()


def demo_ctx():
    c = m.make_ctx()
    for _ in range(3):
        time.sleep(1)
        c.stats.sample()
        c.gpu.sample(c.stats)
    t = time.time()

    art, bg, accent = _prepare_art(cover_art())
    c.media = MediaState(title="Neon Skyline", artist="Les Ondes Polaires", album="Nuits Vectorielles",
                         app="Spotify", playing=True, position=74, duration=212, stamp=t,
                         art=art, bg=bg, accent=accent)

    members = {str(i): {"id": str(i), "name": n, "avatar": None, "mute": mu, "deaf": False,
                        "speaking": sp, "me": i == 0}
               for i, (n, mu, sp) in enumerate([("Moi", False, False), ("Léa", False, True),
                                                ("Tom", True, False), ("Inès", False, False)])}
    dc = c.discord
    dc.status = "connecté"
    dc.voice = {"id": "1", "name": "Général", "guild_id": None, "guild": "Les Copains",
                "members": members}
    dc.notifications = deque([
        {"author": "Léa", "body": "on lance la partie à 21h ? 🎮", "icon": None, "channel": "général",
         "title": "", "time": t - 120},
        {"author": "Tom", "body": "j'arrive dans 5 min 👍", "icon": None, "channel": "général",
         "title": "", "time": t - 300},
        {"author": "Inès", "body": "trop bien la nouvelle map 🔥", "icon": None, "channel": "jeux",
         "title": "", "time": t - 900}])
    dc.unread, dc.self_mute, dc.self_deaf = 2, False, False
    dc.last_notification, dc.voice_event = t - 3600, None
    c.discord_open = True

    c.steam.friends = [{"id": str(i), "name": n, "state": st, "game": g, "avatar": None}
                       for i, (n, st, g) in enumerate([("Léa", "en ligne", "Starfield Tactics"),
                                                       ("Tom", "en ligne", "Rally Horizon"),
                                                       ("Inès", "en ligne", ""),
                                                       ("Max", "absent", "")])]
    c.steam.friends_total, c.steam.friends_status, c.steam.event = 23, "", None
    c.steam.downloads = [
        {"appid": "1", "name": "Starfield Tactics", "state": "téléchargement", "done": 6.2e9,
         "total": 14.4e9, "rate": 38.5 * 2**20},
        {"appid": "2", "name": "Rally Horizon", "state": "en attente", "done": 0, "total": 2.1e9,
         "rate": None}]

    c.sessions = [
        Session(session_id="a", state="working", tool="Edit · render.py", age=3, name="g19-monitor",
                cwd="g19-monitor", context=86000),
        Session(session_id="b", state="waiting", message="Valider le plan ?", age=40,
                name="site-perso", cwd="site-perso", context=41000),
        Session(session_id="c", state="idle", age=420, name="scripts", cwd="scripts", context=12000)]
    git = {"g19-monitor": {"branch": "main", "ahead": 1, "behind": 0, "changed": 3, "untracked": 0,
                           "pr": None},
           "site-perso": {"branch": "refonte-accueil", "ahead": 0, "behind": 0, "changed": 0,
                          "untracked": 1, "pr": {"number": 12, "state": "open", "draft": False,
                                                 "ci": "ok"}}}
    c.git = NS(get=lambda cwd: git.get(cwd))
    c.claude_open = True

    c.notifs = None             # les vraies notifications Windows ne doivent pas apparaître
    if c.weather and c.weather.place:
        c.weather.place = {**c.weather.place, "name": "Lyon", "ip": False}

    # jeu en cours (page GPU) : FPS et temps d'image simulés, capteurs réels
    g = GpuMonitor.__new__(GpuMonitor)
    g.__dict__.update(c.gpu.__dict__)
    g.game = {"pid": 1, "name": "StarfieldTactics.exe", "fps": 141, "frametime_ms": 7.1}
    g.fps_hist = deque([132 + 10 * math.sin(i / 7) - (38 if 92 < i < 101 else 0)
                        for i in range(160)])
    g.ft_hist = deque((24 if i in (60, 61, 140) else 11 if i % 41 == 0 else
                       6.8 + 0.6 * math.sin(i * 1.7)) for i in range(180))
    g.s = {**g.s, "load": 97, "power": 286, "temp": 67, "hotspot": 81}
    c.gpu = g

    c.docker.status = ""
    c.docker.containers = [
        {"id": "1", "name": "postgres", "image": "postgres:16", "state": "running", "status": "Up",
         "cpu": 3.4, "mem": 182e6, "mem_limit": 8e9, "exit": 0, "restarts": 0, "oom": False},
        {"id": "2", "name": "web", "image": "node:22", "state": "running", "status": "Up",
         "cpu": 21.0, "mem": 640e6, "mem_limit": 8e9, "exit": 0, "restarts": 0, "oom": False},
        {"id": "3", "name": "worker", "image": "python:3.13", "state": "restarting",
         "status": "Restarting", "cpu": 0, "mem": 0, "mem_limit": 0, "exit": 1, "restarts": 4,
         "oom": False},
        {"id": "4", "name": "redis", "image": "redis:7", "state": "exited", "status": "Exited",
         "cpu": 0, "mem": 0, "mem_limit": 0, "exit": 0, "restarts": 0, "oom": False}]
    c.batteries.devices = [{"name": "Casque sans fil", "level": 72, "connected": True},
                           {"name": "Manette", "level": 18, "connected": True},
                           {"name": "Souris", "level": 55, "connected": False}]
    c.batteries.status = ""
    return c


def fake_games(c, t):
    """Historique de jeux inventé, sur le modèle des vrais enregistrements."""
    base = dict(c.games.history[0]) if c.games.history else {}
    recs = []
    for i, (name, mins) in enumerate([("Starfield Tactics", 95), ("Rally Horizon", 42),
                                      ("Pixel Dungeon Quest", 18), ("Orbital Racers", 64)]):
        r = {**base, "name": name, "exe": f"demo{i}.exe", "appid": None, "launcher": "steam",
             "duration": mins * 60, "end": t - 3600 * (i + 1) * 5, "start": t - 3600 * (i + 1) * 5 - mins * 60,
             "fps_avg": 140 - i * 20, "fps_low1": 98 - i * 15, "fps_max": 180 - i * 10,
             "temp_max": 70 + i, "cpu_temp_max": 78 + i, "power_avg": 250 - i * 20,
             "fps_curve": [130 + 10 * math.sin(k / 5) for k in range(60)]}
        recs.append(r)
    c.games.history = recs
    c.games.image = lambda rec, kind: None
    return recs


def shot(name, img):
    img.resize((img.width * SCALE, img.height * SCALE), Image.NEAREST).save(OUT / f"{name}.png")


def main():
    c = demo_ctx()
    t = time.time()
    recs = fake_games(c, t)
    pages = ["system", "gpu", "media", "audio", "discord", "steam", "claude", "weather",
             "history", "network", "docker", "games", "cores", "batteries"]
    base = settings.load()
    c.settings = {**base, "theme": "g19", "wallpaper_bg": False, "pages": pages}
    for p in pages:
        shot(p, render.render(p, c, t))
    menu = SettingsMenu()
    menu.show(c.settings, m.page_action("system", c))
    shot("menu", render.render_menu(menu, c, t))
    cov = Coverflow()
    cov.show(pages, "media")
    for _ in range(40):
        img = cov.render(c, t, lambda: m.settings_preview(c, "media"))
        t += 0.05
    shot("coverflow", img)
    shot("recap", render.render_recap(c, recs[0], t, t))
    aw = Away()
    aw.since, aw.locked = t - 3 * 3600, True
    aw.items = [{"source": "Discord", "title": "Léa", "body": "on lance la partie à 21h ? 🎮",
                 "icon": None, "color": "discord", "at": t - 5000},
                {"source": "Claude", "title": "g19-monitor", "body": "a fini", "icon": None,
                 "color": "claude", "at": t - 4000},
                {"source": "Steam", "title": "Rally Horizon", "body": "téléchargement terminé",
                 "icon": None, "color": "steam", "at": t - 3000},
                {"source": "Steam", "title": "Tom", "body": "est en ligne", "icon": None,
                 "color": "steam", "at": t - 2000}]
    c.away = aw
    shot("idle", render.render_idle(c, t))
    shot("away", render.render_away(c, (aw.items, aw.since, t, t), t))
    c.away = None

    # tous les thèmes sur la page GPU (jauges, graphes et panneaux changent selon le thème)
    themes = list(render.THEMES)
    cols = 3
    rows = (len(themes) + cols - 1) // cols
    grid = Image.new("RGB", (cols * 330, rows * 268), (255, 255, 255))
    gd = ImageDraw.Draw(grid)
    label = render.font(13, True)
    for k, th in enumerate(themes):
        c.settings = {**base, "theme": th, "wallpaper_bg": False, "pages": pages}
        x, y = (k % cols) * 330 + 5, (k // cols) * 268 + 22
        grid.paste(render.render("gpu", c, t), (x, y))
        gd.text((x, y - 18), render.THEME_LABELS[th], font=label, fill=(30, 30, 30))
    grid.save(OUT / "themes.png")

    # bandeau d'en-tête : trois écrans dans trois thèmes
    hero = Image.new("RGB", (3 * 640 + 2 * 24, 480), (255, 255, 255))
    for k, (th, p) in enumerate((("g19", "system"), ("aero", "media"), ("analog", "gpu"))):
        c.settings = {**base, "theme": th, "pages": pages}
        hero.paste(render.render(p, c, t).resize((640, 480), Image.NEAREST), (k * 664, 0))
    hero.save(OUT / "hero.png")
    print("captures :", OUT)


if __name__ == "__main__":
    main()
