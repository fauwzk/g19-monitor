"""Moniteur PC + voyant Claude pour l'écran du Logitech G19.

    python g19_monitor.py                 # affiche sur le G19 (LGS doit tourner)
    pythonw g19_monitor.py                # idem, sans console
    python g19_monitor.py --restart       # arrête l'instance en cours et relance en arrière-plan
    python g19_monitor.py --stop          # arrête l'instance en cours
    python g19_monitor.py --preview out   # écrit out/<page>.png au lieu du LCD

Boutons du G19 : ◄ ► changer de page · Annuler revenir à la première page.
Média : ▲ précédent, OK lecture/pause, ▼ suivant. Discord : OK muet, ▲ sourdine.
Claude : ▲ ▼ défiler. Les réglages (config_g19.pyw) sont relus à chaud, et l'appli se
relance d'elle-même quand son code est modifié.
"""
import argparse
import logging
import logging.handlers
import os
import py_compile
import sys
import threading
import time
from pathlib import Path

from PIL import Image


def _startup_failed():
    """Le code n'a pas pu être chargé (fichier en cours d'écriture pendant une mise à jour…) :
    on le note dans g19.log et on réessaie un peu plus tard, au lieu de mourir sans bruit."""
    import subprocess
    import traceback
    here = Path(__file__).resolve().parent
    tries = int(os.environ.get("G19_START_RETRY", "0"))
    with open(here / "g19.log", "a", encoding="utf-8") as f:
        f.write(time.strftime("%Y-%m-%d %H:%M:%S") + f" ERROR chargement impossible "
                f"(essai {tries + 1}/6)\n" + traceback.format_exc())
    if tries < 5 and "--preview" not in sys.argv:
        time.sleep(3)
        subprocess.Popen([sys.executable, *sys.argv], cwd=here,
                         env={**os.environ, "G19_START_RETRY": str(tries + 1)},
                         creationflags=subprocess.DETACHED_PROCESS
                         | subprocess.CREATE_NEW_PROCESS_GROUP, close_fds=True)
    sys.exit(1)


try:
    from g19 import config, instance, mixer, night, remote, screen, settings, version
    from g19.alerts import AlertMonitor
    from g19.updater import Updater
    from g19.amd_driver import AmdDriver
    from g19.docker_mon import DockerMonitor
    from g19.fuel import FuelMonitor
    from g19.screencap import ScreenMirror
    from g19.streaming import Streaming
    from g19.away import Away
    from g19.git_status import GitStatus
    from g19.backlight import Backlight, lgs_led_sdk_enabled, lgs_started_at
    from g19.claude_status import claude_running, read_sessions
    from g19.claude_usage import ClaudeUsage
    from g19.steam_live import SteamLive
    from g19.history import History
    from g19.battery import Batteries
    from g19.devices import DeviceWatcher
    from g19.focus import focus_session
    from g19.coverflow import Coverflow
    from g19.netping import Pinger
    from g19.discord import DiscordClient, discord_running
    from g19.games import GameTracker
    from g19.fans import FanControl
    from g19.gpu import GpuMonitor
    from g19.lyrics import Lyrics
    from g19.media import MediaMonitor
    from g19.notifications import WindowsNotifications, flash_kind
    from g19.render import (CLAUDE_ROWS, FAN_CHIPS, GPU_VIEWS, RECAP_SECONDS, Ctx, has_lyrics, ignored,
                            render, render_away, render_fans, render_idle, render_menu, render_recap,
                            render_splash, theme_of, toast_candidates)
    from g19.sysalerts import SystemWatch
    from g19.speedtest import SpeedTest
    from g19.sysinfo import SystemStats
    from g19.launcher import launch, page_action
    from g19.menu import SettingsMenu
    from g19.tray import Tray, open_config
    from g19.volume import VolumeMonitor
    from g19.vpn import VpnMonitor
    from g19.weather import WeatherMonitor
except Exception:
    if __name__ != "__main__":
        raise
    _startup_failed()

log = logging.getLogger("g19")
RELOAD_DELAY = 1.5  # s sans nouvelle modification avant de relancer


def setup_logging():
    handler = logging.handlers.RotatingFileHandler(instance.APP_DIR / "g19.log",
                                                   maxBytes=256_000, backupCount=1,
                                                   encoding="utf-8")
    handlers = [handler] + ([logging.StreamHandler()] if sys.stderr else [])
    logging.basicConfig(level=logging.INFO, handlers=handlers,
                        format="%(asctime)s %(levelname)s %(message)s")


def make_ctx():
    batteries = Batteries()
    return Ctx(stats=SystemStats(), gpu=GpuMonitor(), sessions=[], settings=settings.load(),
               volume=VolumeMonitor(), games=GameTracker(), discord=DiscordClient(),
               notifs=WindowsNotifications(), alerts=AlertMonitor(), speedtest=SpeedTest(),
               weather=WeatherMonitor(lambda: settings.load()["weather_city"]),
               vpn=VpnMonitor(), lyrics=Lyrics(), usage=ClaudeUsage(), steam=SteamLive(),
               history=History(), batteries=batteries, devices=DeviceWatcher(batteries),
               net=Pinger(lambda: settings.current().get("ping_target")),
               sysw=SystemWatch(settings.current), git=GitStatus(), away=Away(),
               streaming=Streaming(), docker=DockerMonitor(), mirror=ScreenMirror(),
               fuel=FuelMonitor(),
               driver=AmdDriver(),
               updater=Updater(instance.APP_DIR,
                               lambda: settings.current().get("auto_update", True)))


def preview(out_dir):
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    c = make_ctx()
    media = MediaMonitor()
    for _ in range(3):
        time.sleep(1)
        c.stats.sample()
        c.gpu.sample(c.stats)
        c.gpu.sample_fps()
    c.sessions, c.media = read_sessions(), media.state
    for page in settings.PAGE_TITLES:
        path = out / f"{page}.png"
        render(page, c).resize((640, 480), 0).save(path)
        print(path)


def connect_lcd(inst, tray):
    """Attend que Logitech Gaming Software soit prêt (utile juste après l'ouverture de session)."""
    from g19.lcd import G19LCD

    warned = False
    while not inst.quit_requested():
        try:
            return G19LCD("PC Monitor")
        except (OSError, RuntimeError) as e:
            if not warned:
                log.warning("LCD indisponible (%s), nouvel essai toutes les 5 s", e)
                tray.icon.title = "G19 Monitor — en attente de Logitech Gaming Software"
                warned = True
        end = time.time() + 5
        while time.time() < end:
            if any(cmd[0] == "quit" for cmd in drain(tray)):
                return None
            time.sleep(0.2)
    return None


class Splash:
    """Écran de démarrage animé sur le G19 pendant l'initialisation (au moins MIN secondes au
    vrai lancement, juste le temps du chargement après une relance pour mise à jour), avec un
    fondu de sortie."""
    MIN = 2.8
    FADE = 0.3

    def __init__(self, lcd, cfg, short=False):
        self.lcd, self.cfg = lcd, cfg
        self.theme = theme_of(cfg)
        self.start = time.time()
        self.min = 0 if short else self.MIN
        self.progress, self.label = 0.05, "démarrage…"
        self.version = version.label()
        self._done = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def step(self, label, progress):
        self.label, self.progress = label, progress

    def _frame(self, shown, now, fade=1.0):
        img = render_splash(shown, self.label, now, self.theme,
                            None if self.min == 0 else now - self.start, fade, self.version)
        self.lcd.show(screen.adjust(img, self.cfg))
        self.lcd.update()

    def _run(self):
        shown = 0.05
        try:
            while not self._done.is_set() or time.time() - self.start < self.min or shown < 0.99:
                if self._done.is_set():
                    self.progress, self.label = 1.0, "prêt"
                shown += (self.progress - shown) * 0.25    # glisse vers l'avancement réel
                self._frame(shown, time.time())
                time.sleep(1 / 30)
            if self.min:
                end = time.time() + self.FADE
                while time.time() < end:
                    self._frame(1.0, time.time(), (end - time.time()) / self.FADE)
                    time.sleep(1 / 30)
        except Exception:
            return

    def finish(self):
        self._done.set()
        self._thread.join(timeout=self.MIN + 2)


def settings_preview(c, page):
    """Miniature de la carte « Paramètres » du coverflow."""
    m = SettingsMenu()
    m.show(c.settings, page_action(page, c))
    m.index = m.selectable[0]
    return render_menu(m, c, time.time())


def drain(tray):
    cmds = []
    while not tray.commands.empty():
        cmds.append(tray.commands.get())
    return cmds


def tooltip(c, page):
    s = c.gpu.s
    parts = [f"CPU {c.stats.cpu:.0f}%", f"GPU {s.get('load', c.stats.gpu):.0f}%"]
    if s.get("temp"):
        parts[-1] += f" {s['temp']:.0f}°C"
    if c.gpu.game:
        parts.append(f"{c.gpu.game['fps']:.0f} FPS")
    lines = ["G19 Monitor — " + settings.PAGE_TITLES.get(page, page), " · ".join(parts)]
    if c.sessions:
        n = {}
        for sess in c.sessions:
            n[sess.state] = n.get(sess.state, 0) + 1
        labels = {"waiting": "en attente", "working": "au travail", "idle": "terminé"}
        lines.append("Claude : " + ", ".join(f"{v} {labels.get(k, k)}" for k, v in n.items()))
    return "\n".join(lines)


def sources_compile():
    try:
        for path in instance.SourceWatcher._scan():
            py_compile.compile(str(path), doraise=True)
        return True
    except py_compile.PyCompileError as e:
        log.error("code modifié invalide, relance annulée :\n%s", e.msg)
        return False


BLINK_COUNT_KEY = {"done": "blinks_done", "discord": "blinks_discord", "notif": "blinks_notifs",
                   "whatsapp": "blinks_notifs", "snap": "blinks_notifs"}
TEST_FILE = "flash_test.json"   # demandes de test envoyées par l'utilitaire
PULSE_TESTS = ("waiting",)   # tests de pulsation (montrée quelques secondes)
PULSE_TEST_SECONDS = 6


def blink_ms(cfg):
    return settings.blink_ms(cfg.get("blink_ms"), 300)


def backlight_state(c, cfg):
    """Ce que le rétroéclairage doit montrer, par priorité (la nuit : alertes seulement)."""
    if not cfg["backlight"]:
        return None
    if cfg["backlight_alerts"] and c.alerts.active:
        return "alert"
    if c.pulse_test and time.time() < c.pulse_test[1]:
        return c.pulse_test[0]          # test d'une pulsation (menu ou utilitaire)
    if night.quiet(cfg, c.night):
        return None
    states = {s.state for s in c.sessions}
    if cfg["backlight_waiting"] and "waiting" in states:
        return "waiting"
    if cfg["backlight_working"] and "working" in states:
        return "working"
    return None


_task_errors = {}


def guarded(name, fn, *args, **kw):
    """Lance une tâche périodique ; une exception est notée (une fois par 5 min et par tâche)
    au lieu de faire planter la boucle principale."""
    try:
        return fn(*args, **kw)
    except Exception:
        now = time.time()
        if now - _task_errors.get(name, 0) > 300:
            _task_errors[name] = now
            log.exception("tâche « %s » en erreur", name)
        return None


# variables qu'une session Claude Code transmet aux programmes qu'elle lance
AGENT_ENV = ("CLAUDE_CODE_SESSION_ID", "CLAUDE_PID", "CLAUDE_CODE_CHILD_SESSION")
AGENT_WARN_EVERY = 600


def launched_by_agent():
    """Lancée depuis une session Claude Code (directement, ou par une relance d'une instance
    lancée ainsi) ? Son bac à sable peut lui montrer une copie isolée de
    %LOCALAPPDATA%\\G19Monitor : les réglages enregistrés par l'utilitaire ne lui arrivent pas."""
    return any(os.environ.get(k) for k in AGENT_ENV)


BACK_AFTER_GAME = 5      # s après la fin de la partie (sans récapitulatif) avant de revenir


def apply_audio_profile(c, i):
    """Profil audio n° `i` des réglages (icône de la barre des tâches, menu du G19, utilitaire) ;
    le bandeau arrive une fois appliqué par le fil audio."""
    profs = mixer.profiles(c)
    if 0 <= i < len(profs):
        c.volume.do("profile", profs[i])


def page_after_game(page, before, cfg, pages):
    """Page à afficher une fois la partie finie : celle d'avant le jeu, si on est encore sur
    la page en jeu ouverte automatiquement (si on a navigué pendant la partie, on y reste)."""
    if before and page == cfg["game_page"] and before in pages:
        return before
    return page


def check_lgs_lighting(c, now, checked_for):
    """LGS lancé avec « Permettre le contrôle de l'éclairage par le jeu » décochée : le clavier
    ne clignote plus, sans aucune erreur. Bandeau une fois par lancement de LGS (son fichier de
    réglages n'est relu qu'une minute après son démarrage, le temps qu'il l'écrive)."""
    started = lgs_started_at()
    if not started or started == checked_for or now - started < 60:
        return checked_for
    if lgs_led_sdk_enabled() is False:
        log.warning("LGS : « Permettre le contrôle de l'éclairage par le jeu » est décochée, "
                    "le rétroéclairage ne peut pas changer")
        c.lgs_event = ("Rétroéclairage bloqué par LGS",
                       "coche « Permettre le contrôle de l'éclairage par le jeu »", now)
    return started


def visible_pages(c, cfg):
    """Pages réglées, sans celles des applis qui ne tournent pas (Discord, Docker) : elles
    reviennent d'elles-mêmes au lancement de l'appli, le réglage n'est pas touché."""
    hidden = set()
    if not c.discord_open:
        hidden.add("discord")
    if not (c.docker and c.docker.status == ""):     # "" : le moteur Docker répond
        hidden.add("docker")
    if not c.fuel or c.fuel.status == "Home Assistant non configuré":
        hidden.add("fuel")
    return [p for p in cfg["pages"] if p not in hidden] or cfg["pages"][:1]


def start_page(cfg):
    page = settings.load_state().get("page") if cfg["remember_page"] else cfg["start_page"]
    return page if page in cfg["pages"] else cfg["pages"][0]


class Watchdog:
    """Surveille la boucle principale : figée depuis STALL s (blocage dans un pilote, une
    DLL…), on note la pile de chaque fil dans g19.log, on rend les ventilateurs à l'auto (la
    sécurité thermique tourne dans la boucle figée) et on relance une instance neuve."""
    STALL = 45
    PERIOD = 5

    def __init__(self):
        self.beat = time.time()
        self.fans = None
        self._stop = threading.Event()
        threading.Thread(target=self._run, daemon=True, name="watchdog").start()

    def alive(self, now):
        self.beat = now

    def stop(self):
        self._stop.set()

    def _run(self):
        last = time.time()
        while not self._stop.wait(self.PERIOD):
            now = time.time()
            if now - last > self.PERIOD * 3:
                self.beat = now          # PC sorti de veille : la boucle n'était pas figée
            last = now
            if now - self.beat > self.STALL and not self._stop.is_set():
                self._recover(now - self.beat)
                return

    def _recover(self, stalled):
        import faulthandler
        log.error("boucle principale figée depuis %.0f s : relance (piles ci-dessous)", stalled)
        try:
            with open(instance.APP_DIR / "g19.log", "a", encoding="utf-8") as f:
                faulthandler.dump_traceback(file=f, all_threads=True)
        except OSError:
            pass
        if self.fans:   # sans attendre plus de 5 s un verrou tenu par le fil figé
            t = threading.Thread(target=self.fans.close, daemon=True)
            t.start()
            t.join(5)
        try:
            instance.spawn(["--reloaded"], wait_pid=os.getpid())
        finally:
            logging.shutdown()
            os._exit(3)


def run():
    wait_pid = os.environ.pop("G19_WAIT_PID", "")
    if wait_pid.isdigit():   # relance par le chien de garde : l'instance figée doit être partie
        instance.wait_exit(int(wait_pid))
    inst = instance.SingleInstance()
    if inst.already_running:
        log.info("déjà lancé, rien à faire")
        return 0
    if guarded("gardien", instance.ensure_guard):   # relance l'appli si elle plante
        log.info("gardien lancé")
    tray = Tray()
    lcd = connect_lcd(inst, tray)
    if not lcd:
        tray.stop()
        inst.release()
        instance.stopped_on_purpose()     # quittée pendant l'attente de LGS
        return 0
    log.info("démarré (pid %d)", os.getpid())
    agent = launched_by_agent()
    if agent:
        log.warning("lancée depuis une session Claude Code : réglages peut-être isolés de ceux "
                    "de l'utilitaire ; relancer l'appli depuis Windows (start_g19.pyw)")
    agent_warned = 0.0
    lgs_checked_for = None      # lancement de LGS déjà vérifié (une fois par lancement)
    last_guard_check = time.time()
    last_lgs_check = 0.0
    dog = Watchdog()           # couvre aussi le démarrage (écran, capteurs, ventilos)

    watch = settings.Watcher()
    splash = Splash(lcd, watch.settings, short="--reloaded" in sys.argv)
    splash.step("capteurs et services…", 0.2)
    c = make_ctx()
    c.settings = watch.settings
    c.gpu_view = settings.load_state().get("gpu_view") or "both"
    splash.step("ventilateurs…", 0.6)
    c.fans = FanControl()  # seule l'appli pilote les ventilos (pas l'aperçu de l'utilitaire)
    dog.fans = c.fans
    splash.step("média…", 0.8)
    media = MediaMonitor()
    source_watcher = instance.SourceWatcher(background=True)
    keys, mirror = remote.KeyInbox(), remote.Mirror()  # clavier virtuel de l'utilitaire
    page = start_page(c.settings)
    shown_page = page
    last_sample = last_claude = last_watch = last_fps = last_proc = 0.0
    frames, fps_window = 0, time.time()
    game = None
    reload_at = None
    in_game = False
    restart = quit_ = crashed = False
    backlight = Backlight()
    prev_states = {}
    last_discord = last_notif = 0.0
    last_test = time.time()
    menu = SettingsMenu()
    cover = Coverflow()
    recap = None            # (partie terminée, affiché depuis) : récapitulatif de fin de partie
    before_game = None      # page affichée avant l'ouverture automatique de la page en jeu
    left_game_at = None     # fin du jeu (plus de FPS), pour revenir même sans récapitulatif
    pattern_at = None       # mire de réglage de l'écran affichée depuis
    color_test = None       # (effet, "#rrggbb", fin) : couleur essayée depuis l'utilitaire
    last_frame, render_error_at = None, 0.0
    last_ended = c.games.ended
    fan_panel = None        # indice du profil sous le curseur quand le panneau ventilos est ouvert
    splash.finish()
    fps_window = time.time()   # la mesure de fluidité commence après l'écran de démarrage
    try:
        while not inst.quit_requested():
            now = time.time()
            dog.alive(now)
            if now - last_sample >= 1:
                c.night = night.is_night(watch.settings, now)
                c.settings = night.effective(watch.settings, c.night)
            cfg = c.settings
            quiet = night.quiet(cfg, c.night)
            if now - last_sample >= 1:
                guarded("capteurs", c.stats.sample)
                guarded("GPU", c.gpu.sample, c.stats)
                # sécurité : auto forcé tant qu'il fait trop chaud, le profil choisi revient
                # tout seul une fois refroidi (le réglage n'est jamais modifié) ; juste après
                # les capteurs, avant toute autre tâche
                guarded("ventilateurs", c.fans.update, cfg["fan_profile"], c.gpu.s,
                        cfg["fan_safe_cpu"], cfg["fan_safe_gpu"], cfg["fan_recover_seconds"])
                guarded("jeux", c.games.update, c.gpu.game, c.gpu.s, now)
                guarded("alertes", c.alerts.update, c, now)
                guarded("historique", c.history.add, c.stats, c.gpu.s, now)
                guarded("réseau", c.net.check_alert, bool(c.gpu.game), now)
                guarded("absence", lambda: c.away.update(c, now, toast_candidates(c, None, now)))
                if cfg["backlight"] and now - last_lgs_check >= 60:
                    last_lgs_check = now
                    lgs_checked_for = guarded("LGS", check_lgs_lighting, c, now, lgs_checked_for) \
                        or lgs_checked_for
                if now - last_guard_check >= 60:   # gardien arrêté entre-temps : relancé
                    last_guard_check = now
                    guarded("gardien", instance.ensure_guard)
                if agent and now - agent_warned >= AGENT_WARN_EVERY:
                    agent_warned = now
                    c.agent_event = ("Lancée par un agent Claude",
                                     "réglages isolés : quitte-la et relance start_g19.pyw", now)
                profs = mixer.profiles(c)
                guarded("zone de notification", lambda: tray.update(
                    page, visible_pages(c, cfg), c.sessions, tooltip(c, page), c.discord.unread,
                    [p["name"] for p in profs], c.volume.active_profile(profs)))
                last_sample = now
            if now - last_proc >= 5:
                c.claude_open = claude_running()
                c.discord_open = discord_running() or c.discord.status == "connecté"
                last_proc = now
            if now - last_claude >= 0.5:
                c.sessions = read_sessions(now)
                last_claude = now
                # la liste est retriée (état, activité) : le curseur suit la même session
                ids = [s.session_id for s in c.sessions]
                if c.claude_sel_id in ids:
                    c.claude_sel = ids.index(c.claude_sel_id)
                if any(s.state in ("working", "waiting") for s in c.sessions):
                    c.claude_open = True  # Claude Code lancé autrement (WSL, ssh…)
                states = {s.session_id: s.state for s in c.sessions}
                if any(prev_states.get(sid) == "working" and st == "idle"
                       for sid, st in states.items()) and cfg["backlight_done"] and not quiet:
                    backlight.flash("done", cfg["blinks_done"], blink_ms(cfg))
                prev_states = states
            if now - last_watch >= 1:
                last_watch = now
                if watch.poll():
                    c.settings = cfg = watch.settings
                    log.info("réglages rechargés")
                    if settings.last_change_by().startswith("config_g19"):
                        c.saved_event = ("Paramètres enregistrés", "depuis l'utilitaire", now)
                req = config.load(TEST_FILE)
                if not isinstance(req, dict):   # fichier abîmé ou d'un autre format
                    req = None
                if req and req.get("at", 0) > last_test and req.get("kind") == "update":
                    last_test = req["at"]
                    c.updater.check_now()
                if req and req.get("at", 0) > last_test and req.get("kind") == "pattern":
                    last_test = req["at"]
                    pattern_at = time.time()
                if req and req.get("at", 0) > last_test and req.get("kind") in PULSE_TESTS:
                    last_test = req["at"]
                    c.pulse_test = (req["kind"], time.time() + PULSE_TEST_SECONDS, req.get("ms"))
                    color_test = (req["kind"], req.get("color"), time.time() + PULSE_TEST_SECONDS)
                if req and req.get("at", 0) > last_test and req.get("kind") in BLINK_COUNT_KEY:
                    last_test = req["at"]
                    log.info("test de clignotement demandé : %s", req["kind"])
                    count = int(req.get("count") or cfg[BLINK_COUNT_KEY[req["kind"]]])
                    ms = settings.blink_ms(req.get("ms"), blink_ms(cfg))
                    backlight.flash(req["kind"], count, ms)
                    color_test = (req["kind"], req.get("color"), time.time() + count * ms * 2 / 1000 + 1)
                if source_watcher.changed():
                    reload_at = now + RELOAD_DELAY
                elif reload_at and now >= reload_at:
                    reload_at = None
                    if sources_compile():
                        log.info("code modifié, relance")
                        restart = True
                        break

            for cmd in drain(tray):
                if cmd[0] == "page" and cmd[1] in visible_pages(c, cfg):
                    page = cmd[1]
                elif cmd[0] == "speedtest":
                    if "speedtest" in cfg["pages"]:
                        page = "speedtest"
                    c.speedtest.start()
                elif cmd[0] == "audio_profile":
                    apply_audio_profile(c, cmd[1])
                elif cmd[0] == "restart":
                    restart = True
                elif cmd[0] == "quit":
                    quit_ = True
            if restart or quit_:
                break

            pages = visible_pages(c, cfg)
            if c.pages is not None and cfg.get("page_toasts", True):
                back = [p for p in pages if p not in c.pages and p in cfg["pages"]
                        and p in c.pages_hidden]
                if back:   # appli lancée : sa page masquée revient
                    names = " et ".join(settings.PAGE_TITLES.get(p, p) for p in back)
                    c.pages_event = (f"Page {names}", "de nouveau disponible · ◄ ► pour y aller",
                                     now)
            # pages masquées parce que l'appli est vue fermée (pas juste pas encore lue)
            unknown = {"docker"} if c.docker and c.docker.status == "lecture…" else set()
            c.pages_hidden = {p for p in cfg["pages"] if p not in pages and p not in unknown}
            c.pages = pages
            if page not in pages:
                # page masquée (appli fermée) : on revient sur la page voisine dans la liste
                order = cfg["pages"]
                before = order[:order.index(page)] if page in order else []
                page = next((p for p in reversed(before) if p in pages), pages[0])
            if now - last_fps >= 0.25:  # FPS du jeu : 4 lectures/s suffisent
                game = c.gpu.sample_fps()
                last_fps = now
            if page == "gpu" and game:
                c.gpu.sample_frametime()    # graphe des temps d'image : une lecture par image
            if game and not in_game and cfg["game_page"] in pages:
                if page != cfg["game_page"]:
                    before_game = page          # on y reviendra après la partie
                page = cfg["game_page"]
            if in_game and not game:
                left_game_at = now
            elif game:
                left_game_at = None
            in_game = bool(game)

            if c.games.ended is not last_ended:
                last_ended = c.games.ended
                if last_ended and cfg.get("game_recap", True):
                    recap = (last_ended[0], now)
            if recap and now - recap[1] > RECAP_SECONDS:
                recap = None
                page, before_game = page_after_game(page, before_game, cfg, pages), None
            elif before_game and not recap and left_game_at and c.games.session is None and \
                    now - left_game_at > BACK_AFTER_GAME:
                # partie finie sans récapitulatif (option coupée, partie trop courte) ; pas
                # pendant un alt-tab : la session de jeu existe alors encore
                page, before_game = page_after_game(page, before_game, cfg, pages), None
            for b in [*lcd.pressed(), *keys.pressed()]:
                c.away.poke(now)
                if pattern_at:
                    pattern_at = None           # n'importe quelle touche ferme la mire
                    continue
                if recap and not cover.open and not menu.open:
                    recap = None            # n'importe quelle touche ferme le récapitulatif
                    page, before_game = page_after_game(page, before_game, cfg, pages), None
                    continue
                if c.away.summary and not cover.open and not menu.open:
                    c.away.close_summary()  # idem pour le résumé d'absence
                    continue
                if c.away.active and cfg.get("idle_screen", True) and not cover.open                         and not menu.open:
                    continue                # la touche réveille seulement l'écran
                # le carrousel passe avant tout le reste : il recouvre l'écran
                if cover.open:
                    res = cover.handle(b)
                    if res and res[0] == "page":
                        page = res[1]
                    elif res and res[0] == "settings":
                        c.media = media.state
                        menu.update_status = c.updater.status if c.updater else ""
                        profs = mixer.profiles(c)
                        menu.audio_active = c.volume.active_profile(profs)
                        menu.show(cfg, page_action(page, c), profs)
                    continue
                if fan_panel is not None:
                    ids = [pid for pid, _ in FAN_CHIPS]
                    if b in ("left", "up"):
                        fan_panel = (fan_panel - 1) % len(ids)
                    elif b in ("right", "down"):
                        fan_panel = (fan_panel + 1) % len(ids)
                    elif b == "ok" and (saved := guarded("ventilateurs", settings.save_changes,
                                                         {"fan_profile": ids[fan_panel]})):
                        c.settings = cfg = saved
                        watch.poll()
                    elif b in ("cancel", "menu"):
                        fan_panel = None
                    continue
                if page == "audio" and not menu.open and mixer.handle(c, b):
                    continue
                if page == "system" and b == "ok" and not menu.open and c.fans.readings:
                    ids = [pid for pid, _ in FAN_CHIPS]
                    fan_panel = ids.index(cfg["fan_profile"]) if cfg["fan_profile"] in ids else 0
                    continue
                if b == "menu" and not menu.open:
                    cover.show(pages, page)     # Menu : coverflow des écrans + paramètres
                    continue
                if menu.open:
                    # réglages illisibles un instant (écriture en cours ailleurs) : la
                    # touche est perdue, pas l'appli
                    new, cmd = guarded("menu", menu.handle, b, cfg) or (None, None)
                    if new:
                        c.settings = cfg = new      # réglages tels qu'enregistrés
                        watch.poll()
                    if cmd == "config":
                        open_config()
                    elif cmd == "restart":
                        restart = True
                    elif cmd and cmd[0] == "audio_profile":
                        apply_audio_profile(c, cmd[1])
                    elif cmd and cmd[0] == "update":
                        c.updater.check_now()
                        c.saved_event = ("Mises à jour", "vérification sur GitHub…", time.time())
                    elif cmd and cmd[0] == "test" and cmd[1] == "pattern":
                        menu.open = False
                        pattern_at = time.time()
                    elif cmd and cmd[0] == "test" and cmd[1] in PULSE_TESTS:
                        c.pulse_test = (cmd[1], time.time() + PULSE_TEST_SECONDS)
                    elif cmd and cmd[0] == "test":
                        backlight.flash(cmd[1], cfg[BLINK_COUNT_KEY[cmd[1]]], blink_ms(cfg))
                    elif cmd and cmd[0] == "launch":
                        try:
                            launch(cmd[1], cmd[2])
                        except OSError as e:
                            log.warning("lancement de %s impossible : %s", cmd[1], e)
                    continue
                if b in ("left", "right"):
                    step = 1 if b == "right" else -1
                    page = pages[(pages.index(page) + step) % len(pages)]
                elif b == "cancel":
                    page = pages[0]
                elif page == "media" and b == "ok" and (c.show_lyrics or has_lyrics(c)):
                    c.show_lyrics = not c.show_lyrics
                elif page == "media" and b in ("up", "down"):
                    media.command("previous" if b == "up" else "next")
                elif page == "discord" and b == "ok":
                    c.discord.toggle_mute()
                elif page == "discord" and b == "up":
                    c.discord.toggle_deaf()
                elif page == "vpn" and b == "ok":
                    c.vpn.toggle()
                elif page == "speedtest" and b == "ok":
                    c.speedtest.toggle()
                elif page == "notifs" and b == "ok":
                    c.notifs.clear()
                elif page == "claude" and b == "ok":
                    sel = c.sessions[c.claude_sel] if c.claude_sel < len(c.sessions) else None
                    if not (sel and focus_session(sel)):
                        try:
                            launch("claude://")   # pas de fenêtre retrouvée : l'appli Claude
                        except OSError as e:
                            log.warning("ouverture de Claude impossible : %s", e)
                elif page == "gpu" and b == "ok":
                    # graphe en jeu : les deux → FPS → temps d'image ; gardé entre deux lancements
                    views = GPU_VIEWS
                    c.gpu_view = views[(views.index(c.gpu_view) + 1) % len(views)] \
                        if c.gpu_view in views else views[0]
                    guarded("état", settings.save_state, gpu_view=c.gpu_view)
                elif page == "screen" and b == "ok":
                    c.mirror.next_screen()
                elif page == "screen" and b in ("up", "down"):
                    c.mirror.zoom_in(1 if b == "up" else -1)
                elif page == "fuel" and b in ("up", "down"):
                    c.fuel_scroll += 1 if b == "down" else -1
                elif page == "fuel" and b == "ok":
                    c.fuel.check_now()       # relire les prix tout de suite
                elif page == "docker" and b in ("up", "down"):
                    c.docker_scroll += 1 if b == "down" else -1
                elif page == "history" and b == "ok":
                    c.history_view = "load" if c.history_view == "temp" else "temp"
                elif page == "steam" and b in ("up", "down"):
                    c.steam_scroll += 1 if b == "down" else -1
                elif page == "steam" and b == "ok":
                    try:
                        launch("steam://open/friends")
                    except OSError as e:
                        log.warning("ouverture de Steam impossible : %s", e)
                elif page == "claude" and b in ("up", "down"):
                    c.claude_sel += 1 if b == "down" else -1
            # la session choisie reste visible ; la liste défile avec elle
            c.claude_sel = max(0, min(c.claude_sel, len(c.sessions) - 1))
            if c.claude_sel < c.scroll:
                c.scroll = c.claude_sel
            elif c.claude_sel >= c.scroll + CLAUDE_ROWS:
                c.scroll = c.claude_sel - CLAUDE_ROWS + 1
            c.scroll = max(0, min(c.scroll, len(c.sessions) - CLAUDE_ROWS))
            if c.sessions:
                c.claude_sel_id = c.sessions[c.claude_sel].session_id or ""
            if page == "discord":
                c.discord.mark_read()
            if page != "audio":
                c.audio_cursor = None
            if page != shown_page:
                shown_page = page
                guarded("état", settings.save_state, page=page)

            # flash bleu / blanc à l'arrivée d'un message Discord / d'une notification Windows
            if c.discord.last_notification > last_discord:
                last_discord = c.discord.last_notification
                if cfg["backlight"] and cfg["backlight_discord"] and not quiet:
                    backlight.flash("discord", cfg["blinks_discord"], blink_ms(cfg))
            if c.notifs.last_time > last_notif:
                last_notif = c.notifs.last_time
                latest = c.notifs.items[0] if c.notifs.items else None
                # les notifs de l'appli Claude doublonnent le voyant Claude (flash vert) : ignorées
                if (cfg["backlight"] and cfg["backlight_notifs"] and latest and not quiet
                        and not ignored(c, latest) and latest["app"].lower() != "claude"):
                    # WhatsApp en vert, Snapchat en jaune, les autres en blanc
                    backlight.flash(flash_kind(latest), cfg["blinks_notifs"], blink_ms(cfg))
            backlight.speed_ms = blink_ms(cfg)
            backlight.pulse_ms = settings.pulse_ms(cfg["pulse_ms"], 300)
            backlight.colors = {k: settings.hex_to_pct(cfg.get(key)) for k, key
                                in settings.COLOR_KEYS.items() if settings.hex_to_pct(cfg.get(key))}
            if color_test and now < color_test[2] and settings.hex_to_pct(color_test[1]):
                # test depuis l'utilitaire : la couleur affichée là-bas, même pas enregistrée
                backlight.colors[color_test[0]] = settings.hex_to_pct(color_test[1])
            if c.pulse_test and len(c.pulse_test) > 2 and c.pulse_test[2] and now < c.pulse_test[1]:
                # test depuis l'utilitaire : la vitesse du curseur, même pas encore enregistrée
                ms = settings.pulse_ms(c.pulse_test[2], 300)
                backlight.pulse_ms = ms
            backlight.base = settings.hex_to_pct(cfg["backlight_base"])
            backlight.update(backlight_state(c, cfg), cfg["backlight"])
            changes = []
            while not c.volume.changes.empty():
                changes.append(c.volume.changes.get_nowait())
            if changes and cfg.get("device_toasts", True):
                c.devices.audio(changes)       # casque / enceintes / micro branchés ou retirés
            while not c.volume.profile_events.empty():
                name, ok, text = c.volume.profile_events.get_nowait()
                (log.info if ok else log.warning)("profil audio « %s » : %s", name, text)
                c.saved_event = (f"Profil audio · {name}", text, now)
            c.media = media.state
            try:
                if cover.open:
                    frame_img = cover.render(c, now, lambda: settings_preview(c, page))
                elif menu.open:
                    frame_img = render_menu(menu, c, now)
                elif fan_panel is not None:
                    frame_img = render_fans(fan_panel, c, now)
                elif recap:
                    frame_img = render_recap(c, recap[0], now, recap[1])
                elif c.away.summary:
                    frame_img = render_away(c, c.away.summary, now)
                elif c.away.active and cfg.get("idle_screen", True):
                    frame_img = render_idle(c, now)
                else:
                    frame_img = render(page, c, now)
                last_frame = frame_img
            except Exception:
                # une page qui ne se dessine pas ne doit pas arrêter l'appli : on garde l'image
                # précédente et on note l'erreur (une fois par minute au plus)
                if now - render_error_at > 60:
                    render_error_at = now
                    log.exception("erreur de rendu (page %s)", page)
                frame_img = last_frame or Image.new("RGB", (320, 240))
            if pattern_at and now - pattern_at < screen.PATTERN_SECONDS:
                frame_img = screen.pattern(now, pattern_at)   # mire de réglage
            else:
                pattern_at = None
            frame_img = screen.adjust(frame_img, cfg)
            frame_img = night.dim(frame_img, cfg, c.night)
            lcd.show(frame_img)
            mirror.write(frame_img, now)
            frames += 1
            if now - fps_window >= 2:  # fluidité réellement obtenue, affichée dans le menu
                first = menu.real_fps is None
                menu.real_fps = frames / (now - fps_window)
                frames, fps_window = 0, now
                if first:
                    log.info("fluidité : %.1f images/s (réglage %s)", menu.real_fps, cfg["fps"])
            lcd.update()
            time.sleep(max(0.0, 1 / cfg["fps"] - (time.time() - now)))
        log.info("relance" if restart else "arrêt demandé")
    except KeyboardInterrupt:
        pass
    except Exception:
        log.exception("plantage")
        crashed = True
    finally:
        dog.stop()
        # chaque fermeture est protégée : une erreur ici ne doit jamais empêcher la relance
        for step in (c.history.save, c.games.close, c.fans.close, backlight.close, lcd.close,
                     tray.stop):
            try:
                step()
            except Exception:
                log.exception("fermeture : %s", getattr(step, "__qualname__", step))
        if not crashed:
            inst.release()
            if not restart:
                instance.stopped_on_purpose()   # quittée exprès : le gardien s'arrête aussi
    if crashed and instance.guard_running():
        # le gardien relance (aussitôt si le code est corrigé, sinon de plus en plus espacé)
        log.info("plantage : le gardien relancera l'appli")
        inst.release()
    elif crashed:
        # code tout juste modifié et cassé à l'exécution : on attend sa correction pour relancer
        # au lieu de laisser l'écran éteint
        log.info("en attente d'une correction du code pour relancer")
        watcher = instance.SourceWatcher()
        while not inst.quit_requested():
            time.sleep(2)
            if watcher.changed():
                time.sleep(RELOAD_DELAY)
                watcher.changed()
                if sources_compile():
                    restart = True
                    break
        inst.release()
    if restart:
        try:
            instance.spawn(["--reloaded"])
            log.info("nouvelle instance lancée")
        except Exception:
            log.exception("relance impossible")
    return 0


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("--preview", metavar="DOSSIER", help="rendre les pages en PNG au lieu du LCD")
    ap.add_argument("--stop", action="store_true", help="arrêter l'instance en cours")
    ap.add_argument("--restart", action="store_true",
                    help="arrêter l'instance en cours et relancer en arrière-plan")
    ap.add_argument("--reloaded", action="store_true", help=argparse.SUPPRESS)
    args = ap.parse_args()
    setup_logging()

    if args.preview:
        preview(args.preview)
    elif args.stop or args.restart:
        was_running = instance.is_running()
        if not instance.stop():
            print("l'instance en cours ne répond pas")
            return 1
        if args.restart:
            instance.spawn()
            print("relancé" if was_running else "lancé")
        else:
            end = time.time() + 8   # le gardien part avec l'appli (désinstallation : dossier libre)
            while instance.guard_running() and time.time() < end:
                time.sleep(0.2)
            print("arrêté" if was_running else "n'était pas lancé")
    else:
        return run()
    return 0


if __name__ == "__main__":
    code = main()
    logging.shutdown()
    if sys.stdout:
        sys.stdout.flush()
    # sortie franche : aucun thread de fond (tray, COM, Discord…) ne doit garder le processus
    os._exit(code or 0)
