"""Réglages modifiables (par l'utilitaire config_g19.pyw), relus à chaud par l'appli.

Ils vivent dans %LOCALAPPDATA%/G19Monitor/settings.json, hors du code : une mise à jour ou une
modif du code ne les touche pas. Chaque enregistrement garde la version précédente dans
settings.bak.json, reprise si le fichier principal est illisible."""
import json
import os
import shutil
import sys
import threading
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
    "procs": "Processus",
    "fuel": "Carburant",
    "agenda": "Agenda",
    "home": "Maison",
    "daily": "Bilan",
    "toasts": "Bandeaux",
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
    "pause_toasts": True,            # bandeau quand la musique est mise en pause ou reprend
    "device_toasts": True,           # bandeau à la connexion d'un périphérique
    "voice_toasts": True,            # bandeau quand quelqu'un rejoint / quitte l'appel Discord
    "steam_toasts": True,            # bandeau quand un ami Steam se connecte ou lance un jeu
    "achievements": True,            # succès Steam débloqués en jeu : bandeau et récapitulatif
    "stream_toasts": True,           # bandeau quand quelqu'un se connecte en streaming
    "game_blacklist": ["obs"],       # jamais traités comme des jeux (début du nom d'exécutable)
    "screen_list_style": "coverflow",  # touche Menu : coverflow, flat, grid, list
    "screen_dither": True,           # tramage : dégradés sans bandes sur l'écran 16 bits
    "volume_popup": True,            # fenêtre de volume sur le G19 quand le son change
    "mic_popup": True,               # fenêtre sur le G19 quand le micro est coupé / rétabli
    "headset_mic": True,             # micro du casque HyperX (coupé / ouvert) dans la barre du haut
    "animations": True,              # animation entre pages, fondus à l'ouverture des écrans
    "animation_style": "slide",      # g19/anim.py : slide, fade, zoom, wipe, cube, blinds, none
    "animation_speed": "normal",     # fast, normal, slow
    "claude_reminders": True,        # rappel (bandeau + clavier) : Claude attend depuis 10 min
    "rain_toasts": True,             # bandeau « pluie dans ~30 min »
    "day_recap_hour": 21,          # bandeau « Bilan du jour » à cette heure (0 : aucun)
    "smooth_shapes": True,           # formes lissées (anticrénelage) sur le G19
    "headset_auto_switch": True,     # casque branché / allumé : on passe dessus, puis retour
    "agenda_remind": 10,             # rappel N min avant un événement de l'agenda (0 : aucun)
    "ha_entities": [],               # appareils Home Assistant de la page Maison (vide : auto)
    "fuel_toasts": True,             # bandeau quand un carburant est en rupture ou revient
    "fuel_main": "",                 # carburant mis en avant (vide : le plus courant)
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
    "idle_on_lock": True,            # PC verrouillé : écran de repos tout de suite
    "idle_in_video": False,          # écran de repos même pendant une vidéo plein écran
    "idle_style": "clock",           # clock, minimal, seconds, daily, media, page
    "idle_weather": True,            # météo / bilan sous l'horloge
    "idle_events": True,             # ce qui est arrivé pendant l'absence, en bas
    "idle_drift": False,             # l'écran de repos se décale un peu chaque minute
    "idle_dim_minutes": 0,           # sur l'écran de repos depuis N min : assombri (0 : jamais)
    "idle_dim_level": 30,            # luminosité une fois assombri (%)
    "idle_off_minutes": 0,           # sur l'écran de repos depuis N min : écran noir (0 : jamais)
    "away_summary_seconds": 45,      # le résumé d'absence se ferme après (0 : à la touche)
    "game_recap_seconds": 20,        # le récapitulatif de partie se ferme après (0 : à la touche)
    "back_after_game_seconds": 5,    # retour à la page d'avant après une partie sans récap
    "game_grace_seconds": 90,        # s sans images avant de considérer le jeu fermé
    "volume_popup_seconds": 1.6,     # fenêtre de volume / micro affichée tant de secondes
    "claude_remind_minutes": 10,     # rappel « Claude attend » après, puis toutes les N min
    "rain_ahead_minutes": 45,        # bandeau pluie jusqu'à N min avant
    "alert_sustain_seconds": 5,      # au-dessus du seuil depuis N s avant l'alerte
    "update_check_minutes": 15,      # vérification des mises à jour toutes les N min
    "auto_cycle_seconds": 0,         # pages qui défilent seules toutes les N s (0 : non)
    "auto_cycle_in_game": False,     # défilement aussi pendant une partie
    "return_page_minutes": 0,        # sans touche depuis N min : retour à return_page (0 : non)
    "return_page": "system",
    "menu_close_seconds": 0,         # menu / liste des écrans fermés après N s sans touche
    "lyrics_offset_ms": 300,         # avance des paroles synchronisées (ms, négatif = retard)
    "marquee_speed": 26,             # défilement des titres trop longs (px/s)
    "marquee_pause": 2.5,            # pause avant chaque défilement (s)
    "art_fade_ms": 450,              # fondu d'une pochette à la suivante (ms, 0 : sec)
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
    "audio_profiles": [],         # [{"name", "out", "out_id", "in", "in_id", "volume"}]
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
    "color_whatsapp": "#00ff40",     # notification WhatsApp (au lieu du blanc)
    "color_snap": "#fff200",         # notification Snapchat
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

def _dur(values, unit, zero=None):
    """[(valeur, libellé)] pour une liste de durées ; `zero` : libellé de la valeur 0."""
    out = []
    for v in values:
        if v == 0 and zero:
            out.append((0, zero))
        elif unit == "s" and v >= 60 and v % 60 == 0:
            out.append((v, f"{v // 60} min"))
        elif unit == "min" and v < 1:
            out.append((v, f"{round(v * 60)} s"))
        elif unit == "min" and v >= 60 and v % 60 == 0:
            out.append((v, f"{v // 60} h"))
        elif unit == "min" and v >= 60:
            out.append((v, f"{v // 60} h {v % 60:02d}"))
        else:
            out.append((v, f"{v:g} {unit}".replace(".", ",")))
    return out


# choix proposés par l'utilitaire et le menu du G19 pour les réglages de temps
CHOICES = {
    "idle_minutes": _dur([0.5, 1, 2, 3, 4, 5, 7, 10, 15, 20, 25, 30, 45, 60, 90, 120, 180, 240],
                         "min"),
    "away_min_minutes": _dur([0, 1, 2, 3, 5, 10, 15, 20, 30, 45, 60, 120, 240], "min",
                             "toujours"),
    "idle_dim_minutes": _dur([0, 1, 2, 3, 5, 10, 15, 20, 30, 45, 60, 90, 120, 180], "min",
                             "jamais"),
    "idle_off_minutes": _dur([0, 1, 2, 5, 10, 15, 20, 30, 45, 60, 90, 120, 180, 240, 360, 480],
                             "min", "jamais"),
    "idle_dim_level": [(v, f"{v} %") for v in (5, 10, 15, 20, 30, 40, 50, 60, 70, 80)],
    "toast_seconds": _dur([2, 3, 4, 5, 6, 8, 10, 12, 15, 20, 25, 30, 45, 60], "s"),
    "volume_popup_seconds": _dur([0.8, 1, 1.2, 1.6, 2, 2.5, 3, 4, 5, 7, 10], "s"),
    "away_summary_seconds": _dur([0, 10, 15, 20, 30, 45, 60, 90, 120, 180, 300, 600], "s",
                                 "jusqu'à une touche"),
    "game_recap_seconds": _dur([0, 5, 10, 15, 20, 30, 45, 60, 90, 120, 300], "s",
                               "jusqu'à une touche"),
    "back_after_game_seconds": _dur([0, 2, 5, 10, 15, 30, 60, 120, 300], "s", "aussitôt"),
    "game_grace_seconds": _dur([15, 30, 45, 60, 90, 120, 180, 300, 600], "s"),
    "claude_remind_minutes": _dur([1, 2, 3, 5, 10, 15, 20, 30, 45, 60, 120], "min"),
    "rain_ahead_minutes": _dur([15, 30, 45, 60, 75, 90, 105, 120], "min"),
    "alert_sustain_seconds": _dur([0, 2, 5, 10, 15, 30, 60, 120, 300], "s", "aussitôt"),
    "update_check_minutes": _dur([5, 10, 15, 30, 60, 120, 180, 360, 720, 1440], "min"),
    "auto_cycle_seconds": _dur([0, 3, 5, 8, 10, 15, 20, 30, 45, 60, 90, 120, 180, 300, 600],
                               "s", "non"),
    "return_page_minutes": _dur([0, 1, 2, 3, 5, 10, 15, 20, 30, 45, 60, 120], "min", "non"),
    "menu_close_seconds": _dur([0, 5, 10, 15, 20, 30, 45, 60, 120, 300], "s", "jamais"),
    "claude_strip_seconds": _dur([0, 5, 10, 15, 20, 30, 45, 60, 90, 120, 180, 300, 600], "s",
                                 "jamais"),
    "agenda_remind": _dur([0, 1, 2, 5, 10, 15, 20, 30, 45, 60, 90, 120, 180, 1440], "min",
                          "aucun"),
    "fan_recover_seconds": _dur([10, 20, 30, 45, 60, 90, 120, 180, 300, 600, 900], "s"),
    "marquee_speed": [(10, "très lent"), (16, "lent"), (26, "normal"), (40, "rapide"),
                      (60, "très rapide"), (90, "éclair")],
    "marquee_pause": _dur([0, 0.5, 1, 1.5, 2.5, 4, 6, 10], "s"),
    "art_fade_ms": [(0, "sec"), (150, "150 ms"), (300, "300 ms"), (450, "450 ms"),
                    (700, "700 ms"), (1000, "1 s"), (1500, "1,5 s"), (2500, "2,5 s")],
    "day_recap_hour": [(0, "aucun")] + [(h, f"{h} h") for h in range(1, 24)],
}


# écran du PC au repos (render.render_idle)
IDLE_STYLES = {
    "clock": "Horloge, météo et événements",
    "minimal": "Horloge seule",
    "seconds": "Horloge avec les secondes",
    "daily": "Bilan du jour",
    "media": "Média en cours (sinon horloge)",
    "page": "Garder la page affichée",
}


def choices(key, current=None):
    """Choix d'un réglage, avec la valeur actuelle en plus si elle n'y est pas (réglée à la
    main dans settings.json, ou par une ancienne version)."""
    items = list(CHOICES[key])
    if current is not None and all(v != current for v, _ in items):
        items.append((current, f"{current:g} (perso)".replace(".", ",")
                      if isinstance(current, (int, float)) else f"{current} (perso)"))
        items.sort(key=lambda kv: kv[0] if isinstance(kv[0], (int, float)) else 0)
    return items


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
COLOR_KEYS = {"alert": "color_alert", "waiting": "color_waiting", "remind": "color_waiting",
              "working": "color_working",
              "done": "color_done", "discord": "color_discord", "notif": "color_notif",
              "whatsapp": "color_whatsapp", "snap": "color_snap"}


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
          "pixel", "xp", "symbian")


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


def get(key):
    """Un réglage, pour les modules qui n'ont pas les réglages sous la main ; la valeur par
    défaut s'il manque ou n'est pas un nombre alors qu'on en attend un."""
    value = current().get(key, DEFAULTS.get(key))
    default = DEFAULTS.get(key)
    if isinstance(default, (int, float)) and not isinstance(default, bool):
        try:
            return float(value)
        except (TypeError, ValueError):
            return float(default)
    return value


def num(cfg, key):
    """Réglage numérique lu dans `cfg`, la valeur par défaut s'il est absent ou invalide."""
    try:
        return float(cfg.get(key, DEFAULTS[key]))
    except (TypeError, ValueError):
        return float(DEFAULTS[key])


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


_state_lock = threading.Lock()


def save_state(**kw):
    # lire-modifier-écrire sous verrou : la boucle de l'écran et le fil des mises à jour
    # écrivent tous deux dans state.json
    with _state_lock:
        state = load_state()
        state.update(kw)
        config.save("state.json", state)
