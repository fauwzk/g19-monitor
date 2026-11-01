"""Captures du README (docs/images) avec des données de démonstration : capteurs réels (rien
de personnel), mais média, Discord, Steam, sessions Claude, jeux, ville… inventés.
Ne jamais publier de captures faites avec les vraies données (comptes, amis, pochettes).

    python tools/readme_shots.py
"""
import io
import math
import queue
import sys
import threading
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
    demo_extras(c, t)
    # copies figées : les vrais modules continuent de tourner en tâche de fond et
    # écraseraient les données inventées pendant la génération (Discord, Steam, Docker…)
    for name in ("discord", "steam", "docker", "batteries", "away", "streaming", "alerts"):
        obj = getattr(c, name, None)
        if obj is not None and not isinstance(obj, NS):
            frozen = obj.__class__.__new__(obj.__class__)
            frozen.__dict__.update({k: (list(v) if isinstance(v, list) else
                                        deque(v, v.maxlen) if isinstance(v, deque) else v)
                                    for k, v in obj.__dict__.items()})
            setattr(c, name, frozen)
    return c


def demo_extras(c, t):
    """Données inventées pour les autres écrans : rien de ce PC (audio, VPN, météo, réseau,
    usage Claude, carburant…) ne doit se retrouver sur une capture publique."""
    from g19.lyrics import parse_lrc
    from g19.netping import Pinger
    from g19.volume import VolumeMonitor
    from g19.weather import WeatherMonitor

    # audio : sorties, micro et applis inventés (sans le fil audio qui relirait les vrais)
    v = VolumeMonitor.__new__(VolumeMonitor)
    v.__dict__.update(
        device="Haut-parleurs", level=0.62, muted=False, peak=0.45,
        apps={"spotify": 1.0, "discord": 0.8, "firefox": 0.55},
        outputs=[("o1", "Haut-parleurs"), ("o2", "Casque sans fil")], out_id="o1",
        inputs=[("i1", "Micro du casque")], in_id="i1", mic_level=0.8, mic_muted=False,
        mic_peak=0.15, mic_device="Micro du casque", error="", changed_at=0.0,
        mic_changed_at=0.0, changes=queue.Queue(), profile_events=queue.Queue(),
        wake=threading.Event(), _live={}, _cmds=queue.Queue(),
        sessions=[{"key": n, "name": n, "system": s, "volume": vo, "muted": False, "peak": p}
                  for n, s, vo, p in (("Spotify", False, 1.0, 0.6), ("Discord", False, 0.8, 0.2),
                                      ("Firefox", False, 0.55, 0.0),
                                      ("Sons système", True, 0.7, 0.0))])
    c.volume = v
    c.batteries.hyperx = NS(name="Casque sans fil", level=72, charging=0, connected=True,
                            mic_muted=False, mic_changed_at=0.0)

    c.usage = NS(ready=True, block_reset=t + 2.3 * 3600, block_tokens=1.24e6,
                 block_messages=84, week_tokens=18.6e6)
    c.notifs = NS(status="ok", last_time=0, items=[
        {"app": "WhatsApp", "title": "Léa", "body": "on se retrouve à 20 h ?", "icon": None,
         "time": t - 90},
        {"app": "Outlook", "title": "Réunion d'équipe", "body": "demain 10 h · salle 2",
         "icon": None, "time": t - 1500},
        {"app": "Paramètres", "title": "Mises à jour", "body": "redémarrage prévu cette nuit",
         "icon": None, "time": t - 7200}], clear=lambda: None)
    c.dnd = NS(supported=True, active=False, event=None, toggle=lambda: None)

    c.speedtest = NS(phase="done", running=False, live=0.0, progress=1.0, ping=11.8, jitter=1.4,
                     down=938.0, up=612.0, peak=972.0, error="", server="Démo",
                     history=[{"time": t - k * 86400, "ping": 11 + k, "jitter": 1.2,
                               "down": 940 - 30 * k, "up": 610 - 12 * k, "server": "Démo"}
                              for k in range(5)])
    c.vpn = NS(installed=True, busy=False, message="",
               ts={"state": "Running", "running": True, "host": "pc-salon",
                   "ip": "100.64.0.12", "tailnet": "demo.ts.net", "exit": None, "online": 2,
                   "health": [],
                   "peers": [{"name": n, "os": o, "online": on, "ip": ip, "direct": dr,
                              "active": ac, "seen": se}
                             for n, o, on, ip, dr, ac, se in (
                                 ("nas", "linux", True, "100.64.0.2", True, True, 0),
                                 ("portable", "windows", True, "100.64.0.7", False, False, 0),
                                 ("telephone", "android", False, "100.64.0.9", False, False,
                                  3 * 3600))]},
               adapters=[{"name": "Tailscale", "up": True, "ip": "100.64.0.12", "rx": 0, "tx": 0},
                         {"name": "WireGuard", "up": False, "ip": "", "rx": 0, "tx": 0}],
               public={"ip": "203.0.113.42", "city": "Lyon", "isp": "Fibre démo"})

    # météo inventée (pas celle de l'endroit où se trouve ce PC)
    w = WeatherMonitor.__new__(WeatherMonitor)
    h0 = int(t // 3600) * 3600
    day0 = int(t // 86400) * 86400
    w.__dict__.update(place={"name": "Lyon", "ip": False}, status="ok", event=None, updated=t,
                      data={"current": {"temperature_2m": 17.4, "apparent_temperature": 16.1,
                                        "weather_code": 2, "is_day": 1, "wind_speed_10m": 14.0,
                                        "wind_direction_10m": 250, "relative_humidity_2m": 58},
                            "hourly": {"time": [h0 + k * 3600 for k in range(24)],
                                       "temperature_2m": [17 + 3 * math.sin(k / 4) for k in range(24)],
                                       "precipitation_probability": [5, 5, 10, 20, 40, 60, 35, 15] * 3,
                                       "weather_code": [2, 2, 3, 3, 61, 61, 3, 1] * 3,
                                       "is_day": [1] * 6 + [0] * 12 + [1] * 6},
                            "daily": {"time": [day0 + k * 86400 for k in range(5)],
                                      "weather_code": [2, 61, 3, 0, 1],
                                      "temperature_2m_max": [19, 16, 18, 22, 21],
                                      "temperature_2m_min": [9, 10, 8, 11, 12],
                                      "precipitation_probability_max": [10, 70, 30, 0, 5],
                                      "sunrise": [day0 + k * 86400 + 7 * 3600 for k in range(5)],
                                      "sunset": [day0 + k * 86400 + 19 * 3600 for k in range(5)]}})
    c.weather = w

    p = Pinger.__new__(Pinger)
    p.__dict__.update(target="1.1.1.1", status="", event=None, _alerted=0.0,
                      samples=deque([(None if k in (37, 38) else
                                      14 + 3 * math.sin(k / 5) + (22 if k % 29 == 0 else 0))
                                     for k in range(100)]))
    c.net = p

    def fuel(price, out=False):
        return {"price": price, "out": out, "shortage": None, "updated": None, "age": 0}
    c.fuel = NS(status="", event=None, stations={
        "1": {"name": "Station du Centre", "short": "Centre", "city": "Lyon", "brand": "Démo",
              "fuels": {"Gazole": fuel(1.689), "E10": fuel(1.759), "SP98": fuel(1.849)}},
        "2": {"name": "Relais des Quais", "short": "Quais", "city": "Lyon", "brand": "Démo",
              "fuels": {"Gazole": fuel(1.672), "E10": fuel(None, True), "SP98": fuel(1.869)}},
        "3": {"name": "Aire de la Colline", "short": "Colline", "city": "Écully", "brand": "Démo",
              "fuels": {"Gazole": fuel(1.701), "E10": fuel(1.749), "E85": fuel(0.899)}}})

    c.toast_log = deque([
        {"source": "Discord", "title": "Léa · #général", "body": "on lance la partie à 21h ? 🎮",
         "page": "discord", "at": t - 120, "icon": None, "color": [88, 101, 242]},
        {"source": "Claude", "title": "g19-monitor", "body": "attend ta réponse", "page": "claude",
         "at": t - 900, "icon": None, "color": [217, 119, 87]},
        {"source": "Steam", "title": "Rally Horizon", "body": "téléchargement terminé",
         "page": "steam", "at": t - 2400, "icon": None, "color": [102, 192, 244]},
        {"source": "Météo", "title": "Pluie dans ~20 min", "body": "1,2 mm en 15 min · Lyon",
         "page": "weather", "at": t - 5400, "icon": None, "color": None}])

    # recopie d'écran : un bureau dessiné ici
    desk = Image.new("RGB", (320, 180), (24, 60, 110))
    dd = ImageDraw.Draw(desk)
    for y in range(180):
        dd.line((0, y, 320, y), fill=(20 + y // 6, 50 + y // 5, 110 + y // 4))
    dd.rectangle((40, 24, 230, 140), fill=(245, 245, 248), outline=(90, 90, 100))
    dd.rectangle((40, 24, 230, 36), fill=(60, 90, 160))
    for k in range(6):
        dd.rectangle((52, 46 + k * 14, 52 + 40 + (k * 37) % 120, 52 + k * 14), fill=(170, 175, 190))
    dd.rectangle((0, 168, 320, 180), fill=(30, 30, 38))
    c.mirror = NS(frame=desk, status="", label="Écran 1 · 2560×1440", cursor=(150, 90),
                  want=lambda: None)

    lines = ["Les néons s'allument sur la ville", "On roule sans savoir où l'on va",
             "La nuit dessine des lignes", "Et la radio chante tout bas",
             "Horizon violet, moteur qui gronde", "Encore un virage avant l'aube"]
    lrc = "\n".join(f"[01:{10 + 5 * k:02d}.00]{line}" for k, line in enumerate(lines))
    data = {"synced": parse_lrc(lrc), "plain": lines, "instrumental": False}
    c.lyrics = NS(get=lambda m: data)

    # 24 h d'historique et ventilateurs inventés (le dossier de données des captures est vide)
    from g19.history import History
    h = History.__new__(History)
    start = int(t // 60) * 60 - 24 * 3600
    h.__dict__.update(_acc={}, _minute=None, _saved=t, points=[
        {"t": start + k * 60, "cpu": round(25 + 20 * math.sin(k / 90) + (40 if 900 < k < 1060 else 0), 1),
         "gpu": round(10 + (85 if 900 < k < 1060 else 5 * math.sin(k / 50)), 1),
         "cpu_t": round(48 + 10 * math.sin(k / 90) + (22 if 900 < k < 1060 else 0), 1),
         "gpu_t": round(40 + (34 if 900 < k < 1060 else 4 * math.sin(k / 70)), 1)}
        for k in range(24 * 60)])
    c.history = h
    c.fans = NS(error="", applied="auto", event=None, readings=[
        {"id": f"/lpc/fan/{k}", "name": n, "rpm": r, "pump": False, "gpu": g, "control": None,
         "pct": p}
        for k, (n, r, g, p) in enumerate((("CPU Fan", 1180, False, 46), ("System Fan #1", 920, False, 38),
                                          ("System Fan #2", 905, False, 38),
                                          ("System Fan #3", 0, False, None),
                                          ("GPU Fan", 1420, True, 41)))])
    c.steam.root, c.steam.running = "C:/Steam", True


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


GALLERY = ROOT / "docs" / "images" / "themes"
GALLERY_COLS = 4


def screens(c, t, recs, pages):
    """[(libellé, image 320×240)] : tous les écrans du G19 dans le thème réglé dans c."""
    from g19.games import Session as GameSession

    out = []

    def add(label, img):
        out.append((label, img))

    def page(label, p, **attrs):
        saved = {k: getattr(c, k) for k in attrs}
        for k, v in attrs.items():
            setattr(c, k, v)
        try:
            add(label, render.render(p, c, t))
        finally:
            for k, v in saved.items():
                setattr(c, k, v)

    page("Système", "system")
    page("GPU en jeu", "gpu")
    s = GameSession({"path": "demo0.exe", "name": "StarfieldTactics.exe", "pid": 1},
                    {"name": "Starfield Tactics", "launcher": "Steam"}, t - 47 * 60)
    s.last_seen, s.fps = t, [130 + 12 * math.sin(k / 6) for k in range(300)]
    s.temp_max, s.power_sum, s.power_n = 78, 268 * 300, 300
    c.games.session = s
    page("Jeux · en cours", "games")
    c.games.session = None
    page("Jeux · derniers jeux", "games")
    page("Steam", "steam")
    page("Média", "media")
    page("Média · paroles", "media", show_lyrics=True)
    page("Audio", "audio")
    page("Discord", "discord")
    page("Notifications", "notifs")
    c.dnd.active = True
    page("Notifications · ne pas déranger", "notifs")
    c.dnd.active = False
    page("Débit · résultat", "speedtest")
    sp = c.speedtest
    page("Débit · en cours", "speedtest",
         speedtest=NS(**{**sp.__dict__, "phase": "download", "running": True, "live": 712.0,
                         "progress": 0.62, "down": None, "up": None, "peak": 760.0}))
    page("Météo", "weather")
    page("VPN", "vpn")
    page("Claude Code", "claude")
    page("Cœurs du CPU", "cores")
    page("Historique", "history")
    page("Batteries", "batteries")
    page("Réseau", "network")
    page("Docker", "docker")
    page("Carburant", "fuel")
    page("Historique des bandeaux", "toasts")
    page("Recopie d'écran", "screen")

    # par-dessus les pages
    dc = c.discord
    dc.last_notification = t - 1.2
    page("Bandeau (OK ouvre, Annuler ferme)", "system")
    dc.last_notification = t - 3600
    c.volume.changed_at = t - 0.6
    add("Fenêtre de volume", render.volume_popup(render.render("media", c, t), c, t))
    c.volume.changed_at = 0.0
    c.volume.mic_changed_at, c.volume.mic_muted = t - 0.6, True
    add("Fenêtre du micro", render.volume_popup(render.render("system", c, t), c, t))
    c.volume.mic_changed_at, c.volume.mic_muted = 0.0, False

    menu = SettingsMenu()
    menu.show(c.settings, m.page_action("system", c))
    add("Réglages (touche Menu)", render.render_menu(menu, c, t))
    for style, label in (("coverflow", "Carrousel"), ("flat", "Écrans à plat"),
                         ("grid", "Grille des écrans"), ("list", "Liste des écrans")):
        cov = Coverflow()
        cov.show(pages, "media", style)
        tt = t
        for _ in range(40):
            img = cov.render(c, tt, lambda: m.settings_preview(c, "media"))
            tt += 0.05
        add(f"{label} (touche Menu)", img)
    add("Ventilateurs", render.render_fans(0, c, t))
    add("Fin de partie", render.render_recap(c, recs[0], t, t))
    aw = Away()
    aw.since, aw.locked = t - 3 * 3600, True
    aw.items = [{"source": "Discord", "title": "Léa", "body": "on lance la partie à 21h ? 🎮",
                 "icon": None, "color": "discord", "at": t - 5000},
                {"source": "Claude", "title": "g19-monitor", "body": "a fini", "icon": None,
                 "color": "claude", "at": t - 4000},
                {"source": "Steam", "title": "Rally Horizon", "body": "téléchargement terminé",
                 "icon": None, "color": "steam", "at": t - 3000}]
    c.away = aw
    add("PC au repos", render.render_idle(c, t))
    add("Au retour", render.render_away(c, (aw.items, aw.since, t, t), t))
    c.away = None
    add("Démarrage", render.render_splash(1.0, "prêt", t, c.settings["theme"]))
    return out


def gallery(c, t, recs):
    """Une planche par thème avec tous les écrans (docs/images/themes/<thème>.png)."""
    GALLERY.mkdir(parents=True, exist_ok=True)
    pages = list(settings.PAGE_TITLES)
    base = settings.load_defaults()
    title_f, label_f = render.font(20, True), render.font(12, True)
    names = []
    for th in render.THEMES:
        # sans animations : chaque écran figé dans son état final (pas de fondu en cours)
        c.settings = {**base, "theme": th, "wallpaper_bg": False, "pages": pages,
                      "animations": False}
        c.pages = pages
        shots = screens(c, t, recs, pages)
        rows = (len(shots) + GALLERY_COLS - 1) // GALLERY_COLS
        sheet = Image.new("RGB", (GALLERY_COLS * 336 + 16, 48 + rows * 264), (246, 247, 249))
        d = ImageDraw.Draw(sheet)
        d.text((16, 14), f"Thème {render.THEME_LABELS[th]}", font=title_f, fill=(25, 28, 35))
        for k, (label, img) in enumerate(shots):
            x, y = 16 + (k % GALLERY_COLS) * 336, 48 + (k // GALLERY_COLS) * 264
            d.text((x, y), label, font=label_f, fill=(60, 64, 75))
            sheet.paste(img.convert("RGB"), (x, y + 18))
            d.rectangle((x - 1, y + 17, x + 320, y + 258), outline=(200, 204, 212))
        sheet.save(GALLERY / f"{th}.png", optimize=True)
        names.append(th)
    return names, [label for label, _ in shots]


def shot(name, img):
    img.resize((img.width * SCALE, img.height * SCALE), Image.NEAREST).save(OUT / f"{name}.png")


def mono_sheet(c, t):
    """Version G15 / G510 : toutes les pages monochromes et les encadrés, façon écran du
    clavier (docs/images/g15.png)."""
    from g19 import mono
    shots = [(mono.PAGES[p], mono.render(p, c, t)) for p in mono.DEFAULT_PAGES]
    img = mono.render("media", c, t)
    mono.draw_banner(img, ImageDraw.Draw(img), "Discord · Léa", "on lance la partie à 21h ?")
    shots.append(("Bandeau", img))
    img = mono.render("system", c, t)
    mono.draw_volume(img, ImageDraw.Draw(img), 0.62, False)
    shots.append(("Volume", img))
    img = mono.render("media", c, t)
    mono.draw_keys(img, ImageDraw.Draw(img), "media")
    shots.append(("Touches (Média)", img))
    img = mono.render("audio", c, t)
    mono.draw_keys(img, ImageDraw.Draw(img), "audio")
    shots.append(("Touches (Audio)", img))
    sc, cols = 3, 2
    cw, ch = 160 * sc + 16, 43 * sc + 30
    rows = (len(shots) + cols - 1) // cols
    sheet = Image.new("RGB", (cols * cw + 16, rows * ch + 16), (246, 247, 249))
    d = ImageDraw.Draw(sheet)
    label = render.font(13, True)
    for k, (name, im) in enumerate(shots):
        x, y = 16 + (k % cols) * cw, 12 + (k // cols) * ch
        d.text((x, y), name, font=label, fill=(60, 64, 75))
        sheet.paste(mono.lcd_style(im, sc), (x, y + 18))
    sheet.save(OUT / "g15.png", optimize=True)


def main():
    c = demo_ctx()
    t = time.time()
    recs = fake_games(c, t)
    pages = ["system", "gpu", "media", "audio", "discord", "steam", "claude", "weather",
             "history", "network", "docker", "games", "cores", "batteries"]
    base = settings.load_defaults()       # pas les réglages de ce PC (villes, profils…)
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

    mono_sheet(c, t)
    themes, labels = gallery(c, t, recs)
    print(f"galerie : {len(themes)} thèmes × {len(labels)} écrans dans {GALLERY}")
    print("captures :", OUT)


if __name__ == "__main__":
    main()
