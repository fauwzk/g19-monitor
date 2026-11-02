"""G15 Monitor : la version monochrome de l'appli, pour l'écran 160×43 des G15 / G510 / G13.

Elle tourne à côté de G19 Monitor (autre applet, autre instance) : chaque clavier a son
écran. Elle ne garde que ce qui a du sens en 1 bit et ne pilote rien de partagé (ventilateurs,
casque, mises à jour quand l'appli G19 tourne) : capteurs, média, volume, notifications,
météo et sessions Claude, lus de son côté.

    python g15_monitor.py            # lancer (start_g15.pyw : sans console)
    python g15_monitor.py --stop     # arrêter l'instance en cours
    python g15_monitor.py --preview dossier   # images des pages, sans clavier

Les 4 touches sous l'écran : page précédente, page suivante, puis deux actions selon la page
(lecture / suivant sur Média, volume − / + sur Audio). Réglages : config_g15.pyw (ou l'icône
→ Réglages), enregistrés dans g15_settings.json."""
import argparse
import logging
import logging.handlers
import os
import py_compile
import sys
import threading
import time
from pathlib import Path

from PIL import Image, ImageDraw

here = Path(__file__).resolve().parent
sys.path.insert(0, str(here))

from g19 import config, instance, mono  # noqa: E402

SETTINGS_FILE = "g15_settings.json"
DEFAULTS = {"pages": mono.DEFAULT_PAGES, "fps": 8, "banners": True, "volume_popup": True,
            "banner_seconds": 4, "auto_launch": True}
KEYS_SECONDS = 2.0        # rôles des touches affichés après un appui
VOLUME_SECONDS = 1.5
RELOAD_DELAY = 1.5

log = logging.getLogger("g15")


def setup_log():
    handler = logging.handlers.RotatingFileHandler(here / "g15.log", maxBytes=500_000,
                                                   backupCount=1, encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    log.addHandler(handler)
    log.setLevel(logging.INFO)


def load_settings():
    data = config.load(SETTINGS_FILE, None)
    if data is None:          # premier lancement : le fichier est créé, à modifier à la main
        data = dict(DEFAULTS)
        try:
            config.save(SETTINGS_FILE, data)
        except OSError:
            pass
    cfg = {**DEFAULTS, **data}
    cfg["pages"] = [p for p in cfg["pages"] if p in mono.PAGES] or list(DEFAULTS["pages"])
    return cfg


def guarded(name, fn, *args, **kw):
    try:
        return fn(*args, **kw)
    except Exception:
        log.exception("%s", name)
        return None


class Ctx:
    """Sources lues par la version G15 (sous-ensemble de celles de l'appli G19)."""

    def __init__(self):
        from g19 import settings
        from g19.gpu import GpuMonitor
        from g19.media import MediaMonitor
        from g19.notifications import WindowsNotifications
        from g19.sysinfo import SystemStats
        from g19.volume import VolumeMonitor
        from g19.weather import WeatherMonitor

        self.stats = SystemStats()
        self.gpu = GpuMonitor()
        self.media_monitor = MediaMonitor()
        self.media = None
        self.volume = VolumeMonitor()
        self.notifs = WindowsNotifications()
        self.weather = WeatherMonitor(lambda: settings.load()["weather_city"])
        self.sessions = []
        try:
            from g19.dnd import DoNotDisturb
            self.dnd = DoNotDisturb()
        except Exception:
            self.dnd = None


class Banners:
    """Bandeau du moment : notification Windows, morceau, lecture / pause, micro."""

    def __init__(self):
        self.current = None       # (titre, texte, horodatage)
        self.last_notif = None
        self.track = None
        self.playing = None
        self.mic = None

    def push(self, title, body, now):
        self.current = (title, body, now)

    def follow(self, c, now):
        # « Ne pas déranger » : ni notification ni morceau ; le micro reste (on vient d'appuyer)
        quiet = bool(c.dnd and c.dnd.active)
        wn = c.notifs
        if wn and wn.items:
            if self.last_notif is not None and wn.last_time > self.last_notif and not quiet:
                n = wn.items[0]
                self.push(f"{n['app']} · {n['title']}".strip(" ·"), n["body"], now)
            self.last_notif = wn.last_time
        elif self.last_notif is None:
            self.last_notif = wn.last_time if wn else 0
        m = c.media
        if m and m.title:
            track = (m.title, m.artist)
            if quiet:
                pass
            elif self.track is not None and track != self.track:
                self.push(f"♪ {m.title}", m.artist or m.app or "", now)
            elif self.track == track and self.playing is not None and m.playing != self.playing:
                self.push(("Lecture · " if m.playing else "En pause · ") + (m.app or "média"),
                          f"{m.title} — {m.artist}" if m.artist else m.title, now)
            self.track, self.playing = track, m.playing
        v = c.volume
        if v and v.mic_level is not None:
            if self.mic is not None and v.mic_muted != self.mic:
                self.push("Micro coupé" if v.mic_muted else "Micro activé", v.mic_device or "",
                          now)
            self.mic = v.mic_muted


def frame(c, cfg, page, t, banners, keys_at):
    pages = cfg["pages"]
    img = mono.render(page, c, t, pages.index(page) if page in pages else None, len(pages))
    d = ImageDraw.Draw(img)
    v = c.volume
    if cfg["volume_popup"] and v and v.level is not None and 0 <= t - v.changed_at < VOLUME_SECONDS:
        mono.draw_volume(img, d, v.level, v.muted)
    elif cfg["banners"] and banners.current and t - banners.current[2] < cfg["banner_seconds"]:
        mono.draw_banner(img, d, banners.current[0], banners.current[1])
    if t - keys_at < KEYS_SECONDS:
        mono.draw_keys(img, d, page)
    return img


def act(c, page, key):
    """Les deux touches de droite, selon la page."""
    from g19.volume import STEP
    if page == "media" and c.media_monitor:
        c.media_monitor.command("toggle" if key == "b3" else "next")
    elif page == "audio" and c.volume:
        c.volume.do("master", -STEP if key == "b3" else STEP)


def connect_lcd(inst):
    from g19.lcd import MonoLCD
    warned = False
    while not inst.quit_requested():
        try:
            return MonoLCD("PC Monitor (G15)")
        except (OSError, RuntimeError) as e:
            if not warned:
                log.warning("écran monochrome indisponible (%s), nouvel essai toutes les 5 s", e)
                warned = True
            time.sleep(5)
    return None


def sources_compile():
    try:
        for path in instance.source_files(instance.MONO_MAIN):
            py_compile.compile(str(path), doraise=True)
        return True
    except py_compile.PyCompileError as e:
        log.error("code modifié invalide, relance annulée :\n%s", e.msg)
        return False


def open_config():
    """Utilitaire de réglages de la version G15 (config_g15.pyw)."""
    instance._popen([str(here / "config_g15.pyw")])


def make_tray(state):
    """Icône dans la zone de notification : page suivante, réglages, quitter."""
    try:
        import pystray
    except ImportError:
        return None
    img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle((4, 18, 60, 46), 6, fill=(30, 34, 28), outline=(90, 96, 88), width=2)
    d.rectangle((10, 24, 54, 40), fill=(158, 190, 90))
    for k, w in enumerate((30, 20)):
        d.rectangle((13, 27 + k * 6, 13 + w, 30 + k * 6), fill=(30, 34, 28))
    icon = pystray.Icon("G15Monitor", img, "G15 Monitor", menu=pystray.Menu(
        pystray.MenuItem("Page suivante", lambda: state.update(next=True)),
        pystray.MenuItem("Réglages", open_config),
        pystray.MenuItem("Gardien…", lambda: instance._popen([str(here / "config_guard.pyw")])),
        pystray.MenuItem("Quitter", lambda: state.update(quit=True))))
    threading.Thread(target=icon.run, daemon=True, name="icône").start()
    return icon


def run():
    setup_log()
    wait_pid = os.environ.pop("G15_WAIT_PID", "")
    if wait_pid.isdigit():
        instance.wait_exit(int(wait_pid))
    inst = instance.SingleInstance(instance.MONO_MUTEX, instance.MONO_QUIT_EVENT)
    if inst.already_running:
        log.info("déjà lancée")
        return
    log.info("démarrée (pid %s)", os.getpid())
    guarded("gardien", instance.ensure_guard)     # relance l'appli si elle plante
    cfg = load_settings()
    c = Ctx()
    state = {}
    tray = make_tray(state)
    if not instance.is_running():
        # pas d'appli G19 sur ce PC (ou pas lancée) : c'est cette version qui se met à jour
        from g19.updater import Updater
        Updater(instance.APP_DIR, lambda: True)
    lcd = connect_lcd(inst)
    watcher = instance.SourceWatcher(background=True, main=instance.MONO_MAIN)
    banners = Banners()
    page = cfg["pages"][0]
    keys_at = 0.0
    last_sample = last_fps = last_claude = last_cfg = 0.0
    reload_at = None
    restart = False
    from g19.claude_status import read_sessions
    try:
        while lcd and not inst.quit_requested() and not state.get("quit"):
            now = time.time()
            if now - last_cfg >= 2:
                cfg, last_cfg = load_settings(), now
                if page not in cfg["pages"]:
                    page = cfg["pages"][0]
            if now - last_sample >= 1:
                guarded("capteurs", c.stats.sample)
                guarded("GPU", c.gpu.sample, c.stats)
                last_sample = now
            if now - last_fps >= 0.25:
                guarded("FPS", c.gpu.sample_fps)
                last_fps = now
            if now - last_claude >= 0.5:
                c.sessions = guarded("Claude", read_sessions, now) or []
                last_claude = now
            c.media = c.media_monitor.state
            guarded("bandeaux", banners.follow, c, now)

            keys = list(lcd.pressed())
            if state.pop("next", False):
                keys.append("b2")
            for b in keys:
                keys_at = now
                pages = cfg["pages"]
                i = pages.index(page) if page in pages else 0
                if b == "b1":
                    page = pages[(i - 1) % len(pages)]
                elif b == "b2":
                    page = pages[(i + 1) % len(pages)]
                else:
                    guarded("action", act, c, page, b)

            if watcher.changed():
                reload_at = now + RELOAD_DELAY
            elif reload_at and now >= reload_at:
                reload_at = None
                if sources_compile():
                    log.info("code modifié, relance")
                    restart = True
                    break

            img = guarded("rendu", frame, c, cfg, page, now, banners, keys_at)
            if img is not None:
                lcd.show(img)
            lcd.update()
            c.volume.wake.clear()
            c.volume.wake.wait(max(0.0, 1 / max(1, cfg["fps"]) - (time.time() - now)))
    except KeyboardInterrupt:
        pass
    finally:
        on_purpose = bool(state.get("quit")) or inst.quit_requested()
        for step in ((lcd.close if lcd else None), (tray.stop if tray else None)):
            if step:
                try:
                    step()
                except Exception:
                    pass
        inst.release()
    if restart:
        env = {**os.environ, "G15_WAIT_PID": str(os.getpid())}
        instance._popen([str(instance.MONO_MAIN)], env)
    elif on_purpose:
        # quittée exprès (icône, utilitaire, --stop) : le gardien ne la relance pas
        instance.stopped_on_purpose(instance.MONO_GUARD_STOP)
    log.info("arrêtée")


def preview(out_dir):
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    c = Ctx()
    for _ in range(3):
        time.sleep(1)
        c.stats.sample()
        c.gpu.sample(c.stats)
    c.media = c.media_monitor.state
    from g19.claude_status import read_sessions
    c.sessions = read_sessions()
    for p in mono.DEFAULT_PAGES:
        path = out / f"g15_{p}.png"
        mono.lcd_style(mono.render(p, c)).save(path)
        print(path)


def main():
    ap = argparse.ArgumentParser(description="G15 Monitor (écran monochrome 160×43)")
    ap.add_argument("--stop", action="store_true", help="arrêter l'instance en cours")
    ap.add_argument("--preview", metavar="DOSSIER", help="images des pages, sans clavier")
    args = ap.parse_args()
    if args.stop:
        ok = instance.stop(mutex=instance.MONO_MUTEX, quit_event=instance.MONO_QUIT_EVENT)
        print("arrêtée" if ok else "toujours en cours")
    elif args.preview:
        preview(args.preview)
        os._exit(0)
    else:
        run()


if __name__ == "__main__":
    main()
