"""Lancement d'applis depuis le menu du G19 : raccourcis configurés et action liée à la page."""
import os
from pathlib import Path

AFTERBURNER = r"C:\Program Files (x86)\MSI Afterburner\MSIAfterburner.exe"
TASKMGR = r"C:\Windows\System32\Taskmgr.exe"
RIOT_CLIENT = r"C:\Riot Games\Riot Client\RiotClientServices.exe"
RIOT_PRODUCTS = {"league of legends": "league_of_legends", "valorant": "valorant",
                 "legends of runeterra": "bacon"}

DEFAULT_SHORTCUTS = [
    {"name": "Discord", "target": "discord://", "args": ""},
    {"name": "Spotify", "target": "spotify:", "args": ""},
    {"name": "Steam", "target": "steam://open/main", "args": ""},
    {"name": "Gestionnaire des tâches", "target": TASKMGR, "args": ""},
]
MEDIA_APPS = {"spotify": "spotify:", "deezer": "deezer:", "vlc": "vlc"}


def launch(target, args=""):
    """Ouvre un exe, un dossier, une URL ou un lien d'appli (discord://, steam://…)."""
    if args:
        os.startfile(target, arguments=args)
    else:
        os.startfile(target)


def _game_action(games):
    """Relancer le dernier jeu (quand aucun n'est en cours)."""
    if not games or games.session or not games.history:
        return None
    r = games.history[0]
    name = r["name"]
    if r.get("appid"):
        return f"Relancer {name}", f"steam://rungameid/{r['appid']}", ""
    product = RIOT_PRODUCTS.get(name.lower())
    if r.get("launcher") == "Riot" and product and Path(RIOT_CLIENT).exists():
        return (f"Relancer {name}", RIOT_CLIENT,
                f"--launch-product={product} --launch-patchline=live")
    if r.get("exe") and Path(r["exe"]).exists():
        return f"Relancer {name}", r["exe"], ""
    return None


def page_action(page, c):
    """(libellé, cible, arguments) de l'appli liée à la page affichée, ou None."""
    if page == "discord":
        return "Ouvrir Discord", "discord://", ""
    if page in ("media", "lyrics") and c.media and c.media.app:
        target = MEDIA_APPS.get(c.media.app.lower())
        return (f"Ouvrir {c.media.app}", target, "") if target else None
    if page == "games":
        return _game_action(c.games)
    if page == "gpu" and Path(AFTERBURNER).exists():
        return "Ouvrir MSI Afterburner", AFTERBURNER, ""
    if page == "claude":
        return "Ouvrir Claude", "claude://", ""
    if page == "notifs":
        return "Centre de notifications", "ms-actioncenter:", ""
    if page == "steam":
        return "Téléchargements Steam", "steam://open/downloads", ""
    if page == "audio":
        return "Paramètres son", "ms-settings:sound", ""
    if page == "vpn":
        return "Console Tailscale", "https://login.tailscale.com/admin/machines", ""
    if page == "weather":
        return "Météo (navigateur)", "https://open-meteo.com", ""
    if page == "speedtest":
        return "speed.cloudflare.com", "https://speed.cloudflare.com", ""
    if page in ("system", "cores"):
        return "Gestionnaire des tâches", TASKMGR, ""
    return None
