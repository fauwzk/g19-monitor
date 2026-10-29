"""Sauvegarde / restauration des réglages de l'appli dans un fichier .zip (utilitaire)."""
import json
import time
import zipfile

from . import config

SETTINGS = ["settings.json", "state.json"]
SECRETS = ["discord.json", "steam_api.json"]          # accès Discord et clé Steam
HISTORY = ["games.json", "history.json", "speedtest.json", "speedtests.csv",
           "weather_place.json"]
ALLOWED = set(SETTINGS + SECRETS + HISTORY)


def export(path, secrets=True, history=True):
    """Écrit le .zip ; renvoie la liste des fichiers inclus."""
    names = SETTINGS + (SECRETS if secrets else []) + (HISTORY if history else [])
    done = []
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        for name in names:
            f = config.DATA_DIR / name
            if f.exists():
                z.write(f, name)
                done.append(name)
        z.writestr("g19_backup.json", json.dumps({"app": "G19 Monitor", "at": time.time(),
                                                 "files": done}))
    return done


def inspect(path):
    """Contenu d'une sauvegarde : liste des fichiers reconnus ; ValueError si ce n'en est pas."""
    with zipfile.ZipFile(path) as z:
        names = set(z.namelist())
        if "settings.json" not in names:
            raise ValueError("ce fichier n'est pas une sauvegarde G19 Monitor")
        data = json.loads(z.read("settings.json").decode("utf-8"))
        if not isinstance(data, dict):
            raise ValueError("settings.json invalide")
        return sorted(n for n in names if n in ALLOWED)


def restore(path):
    """Remplace les fichiers présents dans la sauvegarde (les autres ne bougent pas), après avoir
    gardé l'état actuel dans avant_import_<date>.zip. Renvoie (fichiers, copie de sécurité)."""
    names = inspect(path)
    safety = config.DATA_DIR / time.strftime("avant_import_%Y%m%d_%H%M%S.zip")
    export(safety)
    with zipfile.ZipFile(path) as z:
        for name in names:
            data = z.read(name)
            if name.endswith(".json"):
                json.loads(data.decode("utf-8"))      # refuse un JSON abîmé
            tmp = config.DATA_DIR / (name + ".tmp")
            tmp.write_bytes(data)
            tmp.replace(config.DATA_DIR / name)
    return names, safety


def describe(names):
    parts = []
    if any(n in names for n in SETTINGS):
        parts.append("réglages")
    if any(n in names for n in SECRETS):
        parts.append("accès Discord / Steam")
    if any(n in names for n in HISTORY):
        parts.append("historiques")
    return ", ".join(parts) or "rien"
