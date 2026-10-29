"""Utilitaire de configuration du moniteur G19 (double-clic pour l'ouvrir).

Interface web (config_ui/index.html) dans une fenêtre native WebView2 (pywebview) ; ce fichier
expose à l'interface les réglages et actions de l'appli. Tout est enregistré à la volée et
appliqué à chaud par l'appli, sans la relancer.
"""
import base64
import io
import os
import sys
import threading
import time
import webbrowser
from datetime import datetime
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(APP_DIR))
os.chdir(APP_DIR)

import webview  # noqa: E402

import install_hooks  # noqa: E402
import install_startup  # noqa: E402
from g19 import afterburner, config, instance, rtss, settings  # noqa: E402
from g19 import discord as discord_rpc  # noqa: E402
from g19.alerts import DEFAULT_THRESHOLDS, RULES  # noqa: E402
from g19.claude_status import read_sessions  # noqa: E402
from g19.launcher import launch  # noqa: E402
from g19.menu import BASE_COLORS, GAME_PAGES  # noqa: E402
from g19.render import BG, render  # noqa: E402
from g19.tray import make_icon  # noqa: E402
from g19.weather import geocode, ip_location  # noqa: E402

UI = APP_DIR / "config_ui" / "index.html"
PORTAL = "https://discord.com/developers/applications"


class Api:
    """Méthodes appelées depuis l'interface (window.pywebview.api.*). Les attributs privés
    (préfixe _) ne sont pas exposés au JavaScript."""

    def __init__(self):
        self._ctx = None
        self._media = None
        self._last_sample = 0.0
        self._window = None
        self._lock = threading.Lock()
        threading.Thread(target=self._load_ctx, daemon=True).start()

    def _load_ctx(self):
        from g19.media import MediaMonitor
        from g19_monitor import make_ctx

        self._ctx = make_ctx()
        self._media = MediaMonitor()

    # --- réglages ---

    def state(self):
        cfg = settings.load()
        dc = config.load(discord_rpc.CONFIG_FILE, {}) or {}
        return {
            "settings": cfg,
            "titles": settings.PAGE_TITLES,
            "rules": {k: list(v) for k, v in RULES.items()},
            "thresholds": {**DEFAULT_THRESHOLDS, **cfg["alerts"]},
            "blinkSpeeds": list(settings.BLINK_SPEEDS),
            "baseColors": BASE_COLORS,
            "gamePages": GAME_PAGES,
            "discord": self._discord_state(dc),
            "startup": install_startup.is_installed(),
            "hooks": install_hooks.is_installed(),
        }

    def save(self, patch):
        """Fusionne `patch` dans les réglages et enregistre."""
        with self._lock:
            s = settings.load()
            s.update(patch)
            settings.save(s)
        return True

    # --- aperçu et état ---

    def preview(self, page):
        c = self._ctx
        if not c:
            return None
        with self._lock:
            now = time.time()
            if now - self._last_sample >= 1:
                self._last_sample = now
                c.stats.sample()
                c.gpu.sample(c.stats)
                c.games.update(c.gpu.game, c.gpu.s, now)
                c.sessions = read_sessions(now)
                c.alerts.update(c, now)
            c.gpu.sample_fps()
            c.media = self._media.state
            cfg = settings.load()
            if page not in cfg["pages"]:
                cfg["pages"] = cfg["pages"] + [page]
            c.settings = cfg
            img = render(page, c, now)
        buf = io.BytesIO()
        img.save(buf, "PNG")
        return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()

    def status(self):
        c = self._ctx
        sources = []
        if c:
            steam = c.games.steam
            sources = [
                ["MSI Afterburner", afterburner.read_sensors() is not None, ""],
                ["RivaTuner (FPS)", rtss.read_apps() is not None, ""],
                ["LibreHardwareMonitor", bool(c.gpu.lhm.sensors), ""],
                ["Steam", bool(steam and steam.apps), f"{len(steam.apps)} jeux" if steam else ""],
                ["Discord", c.discord.status == "connecté", c.discord.status],
                ["Notifications Windows", c.notifs.status == "ok", c.notifs.status],
                ["Audio", c.volume.level is not None, c.volume.device],
                ["Météo", c.weather.status == "ok",
                 (c.weather.place or {}).get("name", c.weather.status)],
            ]
        return {"running": instance.is_running(), "sources": sources}

    # --- appli, démarrage, hooks ---

    def control(self, action):
        if action in ("stop", "restart"):
            instance.stop()
        if action in ("start", "restart") and not instance.is_running():
            instance.spawn()
        return True

    def set_flag(self, which, value):
        module = {"startup": install_startup, "hooks": install_hooks}[which]
        try:
            module.set_installed(bool(value))
            return {"ok": True}
        except OSError as e:
            return {"ok": False, "error": str(e)}

    def open(self, what):
        path = {"log": APP_DIR / "g19.log", "data": config.DATA_DIR, "app": APP_DIR}[what]
        if Path(path).exists():
            os.startfile(path)

    def open_url(self, url):
        webbrowser.open(url)

    # --- Discord ---

    @staticmethod
    def _discord_state(dc):
        exp = dc.get("expires_at")
        return {"clientId": dc.get("client_id", ""), "hasSecret": bool(dc.get("client_secret")),
                "authorized": bool(dc.get("access_token")),
                "expires": datetime.fromtimestamp(exp).strftime("%d/%m/%Y") if exp else ""}

    def discord_authorize(self, client_id, secret):
        dc = config.load(discord_rpc.CONFIG_FILE, {}) or {}
        secret = secret or dc.get("client_secret", "")
        if not client_id or not secret:
            return {"ok": False, "message": "Renseigne le Client ID et le Client Secret."}
        try:
            name = discord_rpc.authorize(client_id, secret)
            return {"ok": True, "message": f"Autorisé pour {name}."}
        except discord_rpc.RpcError as e:
            return {"ok": False, "message": f"Échec : {e}"}
        except Exception as e:
            return {"ok": False, "message": f"Échec de l'échange du jeton : {e}. Vérifie le "
                                            f"secret et la redirection {discord_rpc.REDIRECT_URI}."}

    def discord_forget(self):
        discord_rpc.forget()
        return self._discord_state(config.load(discord_rpc.CONFIG_FILE, {}) or {})

    def discord_portal(self):
        webbrowser.open(PORTAL)

    # --- météo, raccourcis ---

    def check_city(self, city):
        try:
            p = geocode(city) if city else ip_location()
        except Exception:
            return {"ok": False, "message": "Pas de connexion"}
        if not p:
            return {"ok": False, "message": "Ville introuvable"}
        where = ", ".join(x for x in (p["name"], p.get("admin"), p.get("country")) if x)
        return {"ok": True, "message": where + (" — d'après ton adresse IP" if not city else "")}

    def test_shortcut(self, target, args=""):
        try:
            launch(target, args)
            return {"ok": True}
        except OSError as e:
            return {"ok": False, "error": str(e)}

    def browse_exe(self):
        res = self._window.create_file_dialog(
            webview.FileDialog.OPEN, file_types=("Programmes (*.exe;*.lnk)", "Tous (*.*)"))
        return str(Path(res[0])) if res else None


# --- fenêtre -------------------------------------------------------------------------------------

def _native_window_tweaks(window):
    """Barre de titre sombre et icône de l'appli (fenêtre WinForms sous-jacente)."""
    try:
        import ctypes

        hwnd = window.native.Handle.ToInt64()
        on, color = ctypes.c_int(1), ctypes.c_int(0x00261e18)  # BGR de #181e26
        ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, 20, ctypes.byref(on), 4)
        ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, 35, ctypes.byref(color), 4)
    except Exception:
        pass
    try:
        from System.Drawing import Icon  # pythonnet, fourni avec pywebview sous Windows

        ico = config.DATA_DIR / "g19.ico"
        if not ico.exists():
            config.DATA_DIR.mkdir(parents=True, exist_ok=True)
            make_icon().save(ico, sizes=[(16, 16), (32, 32), (48, 48), (64, 64)])
        window.native.Icon = Icon(str(ico))
    except Exception:
        pass


def main():
    api = Api()
    bg = "#%02x%02x%02x" % BG
    window = webview.create_window("G19 Monitor", url=str(UI), js_api=api, width=1280, height=800,
                                   min_size=(1120, 640), background_color=bg)
    api._window = window
    window.events.shown += lambda: _native_window_tweaks(window)
    webview.start(gui="edgechromium", debug="--debug" in sys.argv)


if __name__ == "__main__":
    main()
