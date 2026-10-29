"""Menu « Paramètres » affiché sur le G19 (touche Menu), pour lancer une appli et régler
l'essentiel sans le PC.

▲ ▼ choisir · OK / ► changer · ◄ changer dans l'autre sens · Menu / Annuler fermer.
Les changements sont enregistrés aussitôt (même fichier que config_g19.pyw).
"""
from . import settings
from .night import HOURS

GAME_PAGES = [("", "aucune"), ("gpu", "GPU"), ("games", "Jeux")]
BASE_COLORS = [("#ffffff", "blanc"), ("#00c8ff", "cyan"), ("#4060ff", "bleu"),
               ("#a040ff", "violet"), ("#ff0000", "rouge"), ("#ff4000", "orange"),
               ("#00ff40", "vert"), ("", "éclairage sauvegardé")]

# (clé, libellé, type, options) ; type : bool, int (min, max, pas), choice [(valeur, texte)],
# action (commande), launch ((cible, arguments)), title (séparateur)
SETTINGS_ITEMS = [
    (None, "Rétroéclairage", "title", None),
    ("backlight", "Voyant clavier", "bool", None),
    ("backlight_alerts", "Alertes · rouge", "bool", None),
    ("backlight_waiting", "Claude attend · jaune", "bool", None),
    ("backlight_working", "Claude travaille · orange", "bool", None),
    ("backlight_done", "Claude a fini · vert", "bool", None),
    ("blinks_done", "    clignotements", "int", (1, 10, 1)),
    ("backlight_discord", "Message Discord · bleu", "bool", None),
    ("blinks_discord", "    clignotements", "int", (1, 10, 1)),
    ("backlight_notifs", "Notif Windows · blanc", "bool", None),
    ("blinks_notifs", "    clignotements", "int", (1, 10, 1)),
    ("backlight_base", "Couleur au repos", "choice", BASE_COLORS),
    ("blink_ms", "Clignotement (ms, bas = rapide)", "int", (60, 1000, 20)),
    ("pulse_ms", "Pulsation Claude (ms, bas = rapide)", "int", (30, 300, 10)),
    ("test_waiting", "Tester · pulsation Claude attend", "action", ("test", "waiting")),
    ("test_done", "Tester · vert (Claude a fini)", "action", ("test", "done")),
    ("test_discord", "Tester · bleu (Discord)", "action", ("test", "discord")),
    ("test_notif", "Tester · blanc (notif Windows)", "action", ("test", "notif")),
    (None, "Écran", "title", None),
    ("theme", "Thème", "choice", [("dark", "sombre"), ("light", "clair"), ("g19", "G19 (origine)"),
                                  ("g15", "rétro G15"), ("neon", "néon"),
                                  ("dynamic", "dynamique"), ("contrast", "haut contraste"), ("glacier", "glacier"), ("braise", "braise"),
                                  ("terminal", "terminal"), ("red", "rouge nuit"),
                                  ("aero", "aero (verre)"), ("analog", "cadrans"),
                                  ("hud", "HUD cockpit"), ("tron", "tron"), ("paper", "papier"),
                                  ("paper_dark", "papier sombre"), ("xp", "Windows XP"),
                                  ("pixel", "pixel 8 bits")]),
    ("wallpaper_bg", "Fond d'écran Windows derrière", "bool", None),
    ("wallpaper_dim", "    assombri à (%)", "int", (0, 90, 5)),
    ("discord_toasts", "Bandeau Discord", "bool", None),
    ("win_toasts", "Bandeau notifs Windows", "bool", None),
    ("media_toasts", "Bandeau changement de média", "bool", None),
    ("device_toasts", "Bandeau périphérique connecté", "bool", None),
    ("voice_toasts", "Bandeau arrivée / départ en vocal", "bool", None),
    ("steam_toasts", "Bandeau ami Steam connecté", "bool", None),
    ("stream_toasts", "Bandeau connexion streaming", "bool", None),
    ("docker_toasts", "Bandeau conteneur Docker en panne", "bool", None),
    ("page_toasts", "Bandeau page de nouveau dispo", "bool", None),
    ("driver_toasts", "Bandeau nouveau pilote AMD", "bool", None),
    ("sys_alerts", "Alertes système (MAJ, disque)", "bool", None),
    ("disk_free_gb", "    disque plein sous (Go)", "int", (1, 200, 1)),
    ("game_recap", "Récap de fin de partie", "bool", None),
    ("idle_screen", "Horloge PC au repos", "bool", None),
    ("idle_minutes", "    inactif après (min)", "int", (1, 120, 1)),
    ("away_summary", "Résumé au retour", "bool", None),
    ("alerts_on", "Alertes de seuil", "bool", None),
    ("toast_seconds", "Durée des bandeaux (s)", "int", (2, 30, 1)),
    ("claude_strip_seconds", "Claude au repos après (s)", "int", (0, 600, 5)),
    ("game_page", "Page au lancement d'un jeu", "choice", GAME_PAGES),
    ("remember_page", "Rouvrir sur la dernière page", "bool", None),
    ("fps", "Fluidité (images/s)", "int", (5, 60, 5)),
    ("ping_target", "Cible du ping (Réseau)", "choice",
     [("1.1.1.1", "Cloudflare 1.1.1.1"), ("8.8.8.8", "Google 8.8.8.8"),
      ("9.9.9.9", "Quad9 9.9.9.9")]),
    (None, "Réglage de l'écran", "title", None),
    ("screen_brightness", "Luminosité (%)", "int", (50, 150, 5)),
    ("screen_contrast", "Contraste (%)", "int", (50, 150, 5)),
    ("screen_gamma", "Tons sombres (gamma %)", "int", (60, 160, 5)),
    ("screen_saturation", "Saturation (%)", "int", (0, 200, 10)),
    ("screen_sharpen", "Netteté renforcée", "bool", None),
    ("test_pattern", "Afficher la mire", "action", ("test", "pattern")),
    (None, "Mode nuit", "title", None),
    ("night_mode", "Mode nuit", "bool", None),
    ("night_start", "Début de la nuit", "choice", [(h, h) for h in HOURS]),
    ("night_end", "Fin de la nuit", "choice", [(h, h) for h in HOURS]),
    ("night_dim", "Luminosité la nuit (%)", "int", (10, 100, 10)),
    ("night_theme", "Thème la nuit", "choice",
     [("", "inchangé"), ("dark", "sombre"), ("g19", "G19"), ("light", "clair"),
      ("g15", "rétro G15"), ("neon", "néon"), ("dynamic", "dynamique"),
      ("red", "rouge nuit"), ("contrast", "haut contraste"), ("glacier", "glacier"),
      ("braise", "braise"), ("terminal", "terminal"), ("hud", "HUD cockpit"),
      ("analog", "cadrans"), ("paper", "papier"), ("paper_dark", "papier sombre")]),
    ("night_quiet", "Clavier discret la nuit", "bool", None),
    (None, "Ventilateurs", "title", None),
    ("fan_profile", "Profil (via LHM)", "choice",
     [("auto", "auto (GCC)"), ("silent", "silencieux"), ("balanced", "équilibré"),
      ("performance", "performance"), ("max", "maximum")]),
    ("fan_safe_cpu", "Retour en auto : CPU (°C)", "int", (60, 100, 1)),
    ("fan_safe_gpu", "Retour en auto : GPU hotspot (°C)", "int", (60, 100, 1)),
    ("fan_recover_seconds", "Retour au profil après (s)", "int", (10, 900, 10)),
    (None, "Appli", "title", None),
    ("config", "Ouvrir la config sur le PC", "action", "config"),
    ("restart", "Redémarrer l'appli", "action", "restart"),
    ("auto_update", "Mises à jour auto (GitHub)", "bool", None),
    ("update_check", "Vérifier les mises à jour", "action", ("update",)),
]
VISIBLE = 8


class SettingsMenu:
    def __init__(self):
        self.open = False
        self.items = SETTINGS_ITEMS
        self.selectable = []
        self.index = self.top = 0
        self.real_fps = None

    def show(self, cfg, page_action=None):
        """Ouvre le menu ; `page_action` = (libellé, cible, args) lié à la page affichée."""
        launch = []
        if page_action:
            label, target, args = page_action
            launch.append((None, label, "launch", (target, args)))
        for sc in cfg.get("shortcuts", []):
            same = page_action and sc.get("target") == page_action[1]
            if sc.get("name") and sc.get("target") and not same:
                launch.append((None, sc["name"], "launch", (sc["target"], sc.get("args", ""))))
        self.items = ([(None, "Ouvrir", "title", None)] + launch if launch else []) + SETTINGS_ITEMS
        self.selectable = [i for i, it in enumerate(self.items) if it[2] != "title"]
        self.index, self.top = self.selectable[0], 0
        self.open = True

    def value_text(self, item, cfg):
        key, _label, kind, opts = item
        if kind == "bool":
            return "oui" if cfg.get(key) else "non"
        if kind == "int":
            if key == "fps" and self.real_fps:
                return f"{cfg.get(key)} (réel {self.real_fps:.0f})"
            return str(cfg.get(key))
        if kind == "choice":
            value = cfg.get(key)
            return dict(opts).get(value, value or "?")  # couleur perso : affichée en hex
        return "›" if kind in ("action", "launch") else ""

    def handle(self, button, cfg):
        """Traite un bouton. Renvoie (réglages modifiés ou None, commande ou None) ; une
        commande est "config", "restart" ou ("launch", cible, args)."""
        if button in ("menu", "cancel"):
            self.open = False
            return None, None
        pos = self.selectable.index(self.index)
        if button in ("up", "down"):
            pos = (pos + (1 if button == "down" else -1)) % len(self.selectable)
            self.index = self.selectable[pos]
            self._scroll()
            return None, None
        key, _label, kind, opts = self.items[self.index]
        step = -1 if button == "left" else 1
        new = dict(cfg)
        if kind == "bool":
            new[key] = not cfg.get(key)
        elif kind == "int":
            lo, hi, inc = opts
            new[key] = max(lo, min(hi, int(cfg.get(key, lo)) + step * inc))
        elif kind == "choice":
            values = [v for v, _ in opts]
            cur = values.index(cfg.get(key)) if cfg.get(key) in values else 0
            new[key] = values[(cur + step) % len(values)]
        elif kind == "action" and opts[0] == "test" and button in ("ok", "right"):
            return None, opts  # le menu reste ouvert pour enchaîner les tests
        elif kind in ("action", "launch") and button in ("ok", "right"):
            self.open = False
            return None, ("launch", *opts) if kind == "launch" else opts
        else:
            return None, None
        new = settings.save_changes({key: new[key]})
        return new, None

    def _scroll(self):
        # garde la ligne choisie visible, avec son titre de section quand c'est possible
        if self.index < self.top + 1:
            self.top = max(0, self.index - 1)
        elif self.index >= self.top + VISIBLE:
            self.top = self.index - VISIBLE + 1
