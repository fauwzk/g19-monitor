"""Réglages modifiables (par l'utilitaire config_g19.pyw), relus à chaud par l'appli.

Ils vivent dans %LOCALAPPDATA%/G19Monitor/settings.json, hors du code : une mise à jour ou une
modif du code ne les touche pas. Chaque enregistrement garde la version précédente dans
settings.bak.json, reprise si le fichier principal est illisible."""
import json
import os
import shutil
import sys
import time

from . import config
from .launcher import DEFAULT_SHORTCUTS

FILE = "settings.json"
BACKUP = "settings.bak.json"


class Unreadable(Exception):
    """settings.json existe mais n'a pas pu être lu (écriture en cours, fichier abîmé)."""


def _read():
    path = config.DATA_DIR / FILE
    for _ in range(6):
        try:
            return json.loads(path.read_text("utf-8"))
        except FileNotFoundError:
            return {}
        except (OSError, ValueError):
            time.sleep(0.05)    # fichier en cours de remplacement : on réessaie
    data = config.load(BACKUP)
    if isinstance(data, dict):
        return data
    # surtout pas les réglages par défaut : le prochain enregistrement écraserait tout
    raise Unreadable(str(path))

PAGE_TITLES = {
    "system": "Système",
    "gpu": "GPU",
    "games": "Jeux",
    "steam": "Steam",
    "media": "Média",
    "audio": "Audio",
    "discord": "Discord",
    "notifs": "Notifs",
    "speedtest": "Débit",
    "weather": "Météo",
    "vpn": "VPN",
    "claude": "Claude",
    "cores": "Cœurs",
    "history": "Historique",
    "batteries": "Batteries",
    "network": "Réseau",
    "docker": "Docker",
    "screen": "Écran PC",
}

# pages qui existaient avant que les réglages ne mémorisent la liste des pages connues
LEGACY_PAGES = ["system", "gpu", "games", "media", "discord", "claude", "cores"]

DEFAULTS = {
    "pages": list(PAGE_TITLES),      # pages affichées, dans l'ordre
    "remember_page": True,           # rouvrir sur la dernière page affichée
    "start_page": "system",          # sinon, page de démarrage
    "game_page": "gpu",              # page affichée au lancement d'un jeu ("" = ne pas changer)
    "fps": 15,
    "gpu_power_max": 315,
    "discord_toasts": True,          # bandeau sur toutes les pages à l'arrivée d'un message
    "toast_seconds": 6,
    "win_toasts": True,              # bandeau pour les notifications Windows
    "media_toasts": True,            # bandeau au changement de musique / média
    "device_toasts": True,           # bandeau à la connexion d'un périphérique
    "voice_toasts": True,            # bandeau quand quelqu'un rejoint / quitte l'appel Discord
    "steam_toasts": True,            # bandeau quand un ami Steam se connecte
    "stream_toasts": True,           # bandeau quand quelqu'un se connecte en streaming
    "docker_toasts": True,           # bandeau quand un conteneur plante ou boucle
    "page_toasts": True,             # bandeau quand une page masquée (Discord, Docker) revient
    "driver_toasts": True,           # bandeau quand un nouveau pilote AMD est disponible
    "auto_update": True,             # mise à jour depuis le dépôt GitHub (dossier = clone git)
    "sys_alerts": True,              # bandeau : redémarrage Windows requis, disque presque plein
    "disk_free_gb": 15,              # espace libre minimal par disque (Go)
    "game_recap": True,              # récapitulatif à la fin d'une partie
    "idle_screen": True,             # horloge quand le PC est verrouillé ou inactif
    "idle_minutes": 5,               # inactif après tant de minutes sans clavier ni souris
    "away_summary": True,            # au retour, résumé de ce qui est arrivé
    "away_min_minutes": 5,           # absence minimale pour avoir le résumé
    "screen_brightness": 100,        # écran du G19 (%), appliqué à chaque image
    "screen_contrast": 100,
    "screen_gamma": 100,             # > 100 : tons sombres relevés (le LCD les écrase)
    "screen_saturation": 100,
    "screen_sharpen": False,         # netteté renforcée des textes
    "ping_target": "1.1.1.1",        # cible du ping de l'écran Réseau
    "notif_ignore": [],              # applis dont on ignore les notifications Windows
    "alerts_on": True,
    "alerts": {},                    # seuils (voir alerts.DEFAULT_THRESHOLDS), 0 = désactivé
    "backlight": True,               # rétroéclairage du G19 comme voyant
    "backlight_alerts": True,        # clignote en rouge pendant une alerte
    "backlight_waiting": True,       # pulse en jaune quand Claude attend une réponse
    "backlight_working": False,      # orange fixe quand Claude travaille
    "backlight_done": True,          # flash vert quand Claude a fini
    "backlight_discord": True,       # flash bleu à chaque message Discord
    "backlight_notifs": True,        # flash blanc à chaque notification Windows
    "shortcuts": DEFAULT_SHORTCUTS,  # applis à ouvrir depuis le menu du G19
    "blinks_done": 3,                # nombre de clignotements par type d'événement
    "blinks_discord": 3,
    "blinks_notifs": 2,
    "pulse_ms": 200,                 # pulsation jaune « Claude attend » (ms, plus bas = plus vite)
    "blink_ms": 300,                 # durée d'un clignotement (ms, plus bas = plus vite)
    # couleurs du clavier par effet ("#rrggbb")
    "color_alert": "#ff0000",
    "color_waiting": "#ffa600",
    "color_working": "#ff6600",
    "color_done": "#00ff33",
    "color_discord": "#5966ff",
    "color_notif": "#ffffff",
    "backlight_base": "#ffffff",     # couleur de repos après un effet ("" = éclairage sauvegardé)
    "weather_city": "",              # ville de la page météo
    "theme": "",                     # écran du G19 : voir THEMES
    "wallpaper_bg": False,           # fond d'écran Windows (flouté) derrière les pages
    "wallpaper_dim": 60,             # assombrissement du fond d'écran (%), pour la lisibilité
    "light_mode": False,             # ancien réglage (mode clair), repris si theme est vide
    "fan_profile": "auto",
    "fan_safe_cpu": 85,              # °C CPU au-delà desquels les ventilos repassent en auto
    "fan_safe_gpu": 95,              # °C hotspot GPU, idem
    "fan_recover_seconds": 60,       # refroidi depuis tant de secondes : retour au profil choisi
    "claude_strip_seconds": 10,
    "night_mode": False,             # mode nuit entre night_start et night_end
    "night_start": "23:00",
    "night_end": "07:00",
    "night_dim": 40,                 # luminosité de l'écran la nuit (%)
    "night_theme": "",               # thème imposé la nuit ("" = garder le thème)
    "night_quiet": True,             # la nuit, le clavier ne clignote que pour les alertes      # encart Claude masqué N s après la fin du dernier agent (0 = toujours)           # ventilateurs carte mère (via LHM) : voir fans.PROFILES
}

def hex_to_pct(color):
    """'#rrggbb' → (r, g, b) en % pour le SDK, None si vide ou invalide."""
    color = (color or "").lstrip("#")
    if len(color) != 6:
        return None
    try:
        return tuple(round(int(color[i:i + 2], 16) / 255 * 100) for i in (0, 2, 4))
    except ValueError:
        return None


PULSE_RANGE = (30, 300)  # ms par pulsation
# anciens réglages par nom, convertis en ms à la lecture
PULSE_SPEEDS = {"très lent": 1000, "lent": 600, "normal": 300, "rapide": 180,
                "très rapide": 110}


BLINK_RANGE = (60, 1000)  # ms par clignotement
COLOR_KEYS = {"alert": "color_alert", "waiting": "color_waiting", "working": "color_working",
              "done": "color_done", "discord": "color_discord", "notif": "color_notif"}


def blink_ms(value, default=300):
    try:
        return min(BLINK_RANGE[1], max(BLINK_RANGE[0], int(value)))
    except (TypeError, ValueError):
        return default


def pulse_ms(value, default):
    try:
        return min(PULSE_RANGE[1], max(PULSE_RANGE[0], int(value)))
    except (TypeError, ValueError):
        return default
BLINK_SPEEDS = {"lent": 600, "normal": 300, "rapide": 180}  # ms par clignotement


# thèmes de l'écran (voir render.THEMES)
THEMES = ("dark", "light", "g19", "g15", "neon", "dynamic", "contrast", "glacier", "braise",
          "terminal", "red", "aero", "analog", "hud", "tron", "paper", "paper_dark",
          "pixel")


def load():
    s = dict(DEFAULTS)
    raw = _read() or {}
    s.update(raw)
    for old, new in (("pulse_speed", "pulse_ms"),):
        if new not in raw and raw.get(old) in PULSE_SPEEDS:
            s[new] = PULSE_SPEEDS[raw[old]]
    if "blink_ms" not in raw and raw.get("blink_speed") in BLINK_SPEEDS:
        s["blink_ms"] = BLINK_SPEEDS[raw["blink_speed"]]
    # les pages ajoutées depuis le dernier enregistrement sont affichées par défaut
    seen = s.get("pages_seen") or LEGACY_PAGES
    s["pages"] = [p for p in s["pages"] if p in PAGE_TITLES] + \
        [p for p in PAGE_TITLES if p not in seen and p not in s["pages"]]
    s["pages"] = s["pages"] or ["system"]
    if s.get("theme") not in THEMES:
        s["theme"] = "light" if s.get("light_mode") else "dark"
    return s


_current = {"mtime": None, "settings": None}


def current():
    """Réglages actuels, relus seulement quand le fichier change (pour les threads qui en
    ont besoin souvent) ; les valeurs par défaut si le fichier est illisible."""
    try:
        m = (config.DATA_DIR / FILE).stat().st_mtime
    except OSError:
        m = 0
    if m != _current["mtime"] or _current["settings"] is None:
        try:
            _current["settings"] = load()
        except Unreadable:
            return _current["settings"] or load_defaults()
        _current["mtime"] = m
    return _current["settings"]


def last_change_by():
    """Programme à l'origine de la dernière modification (d'après settings_changes.log)."""
    try:
        with open(config.DATA_DIR / JOURNAL, "rb") as f:
            f.seek(0, 2)
            f.seek(max(0, f.tell() - 2048))
            line = f.read().decode("utf-8", errors="replace").strip().splitlines()[-1]
        return line.split("[", 1)[1].split("]", 1)[0]
    except (OSError, IndexError):
        return ""


def load_defaults():
    return {**DEFAULTS, "pages": list(PAGE_TITLES)}


def save(s):
    data = {k: s[k] for k in DEFAULTS if k in s}
    data["pages_seen"] = list(PAGE_TITLES)
    path = config.DATA_DIR / FILE
    before = config.load(FILE, {}) or {}
    try:
        shutil.copyfile(path, config.DATA_DIR / BACKUP)
    except OSError:
        pass
    config.save(FILE, data)
    _journal(before, data)


JOURNAL = "settings_changes.log"


def _journal(before, after):
    """Note chaque réglage modifié, et par quel programme, dans settings_changes.log."""
    changes = [f"{k}: {before.get(k)!r} → {v!r}" for k, v in after.items()
               if k != "pages_seen" and before.get(k) != v]
    if not changes:
        return
    who = os.path.basename(sys.argv[0] or "?")
    line = f"{time.strftime('%Y-%m-%d %H:%M:%S')} [{who}] " + " ; ".join(changes) + "\n"
    try:
        path = config.DATA_DIR / JOURNAL
        if path.exists() and path.stat().st_size > 256 * 1024:
            path.replace(path.with_suffix(".old.log"))
        with open(path, "a", encoding="utf-8") as f:
            f.write(line)
    except OSError:
        pass


def save_changes(changes):
    """Enregistre seulement `changes` par-dessus les réglages actuels du fichier, pour ne pas
    écraser ce qui a été modifié ailleurs (menu du G19, autre fenêtre) entre-temps."""
    s = load()
    s.update(changes)
    save(s)
    return s


class Watcher:
    """Recharge les réglages quand le fichier change."""

    def __init__(self):
        self.path = config.DATA_DIR / FILE
        self.mtime = self._mtime()
        try:
            self.settings = load()
        except Unreadable:
            self.settings, self.mtime = load_defaults(), 0   # relu au prochain poll

    def _mtime(self):
        try:
            return self.path.stat().st_mtime
        except OSError:
            return 0

    def poll(self):
        m = self._mtime()
        if m != self.mtime:
            try:
                self.settings = load()
            except Unreadable:
                return False    # on garde les réglages en mémoire et on réessaiera
            self.mtime = m
            return True
        return False


def load_state():
    return config.load("state.json", {}) or {}


def save_state(**kw):
    state = load_state()
    state.update(kw)
    config.save("state.json", state)
